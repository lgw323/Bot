import asyncio
import logging
import random
import re
from collections import deque
from typing import Optional, List
from datetime import datetime, timedelta
import time
import statistics

import discord
from discord.ext import commands
import yt_dlp

# rapidfuzz 라이브러리가 있으면 제목 유사도 비교에 사용합니다. (성능 향상)
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logging.getLogger("MusicCog").warning("rapidfuzz 라이브러리를 찾을 수 없습니다. 'pip install rapidfuzz'로 설치해야 제목 유사도 비교 기능이 활성화됩니다.")

from .music_utils import (
    Song, LoopMode, LOOP_MODE_DATA,
    BOT_EMBED_COLOR, YTDL_OPTIONS,
    ytdl, load_music_settings, get_network_stats
)
from .music_ui import MusicPlayerView

logger = logging.getLogger("MusicCog")

# 오디오 효과와 그에 따른 재생 속도 배율 정의
AUDIO_EFFECTS = { "none": "", "bassboost": "bass=g=15", "speedup": "rubberband=tempo=1.25", "nightcore": "atempo=1.2,asetrate=48000*1.2", "vaporwave": "atempo=0.8,asetrate=48000*0.85" }
EFFECT_SPEED_FACTORS = { "speedup": 1.25, "nightcore": 1.2, "vaporwave": 0.8 }

class MusicState:
    """
    서버(Guild)별 음악 재생 상태를 관리하는 클래스입니다.
    큐, 볼륨, 현재 곡, 루프 모드 등 모든 상태 정보를 담고 있습니다.
    """
    def __init__(self, bot: commands.Bot, cog, guild: discord.Guild, initial_volume: float = 0.5):
        self.bot, self.cog, self.guild = bot, cog, guild
        self.queue = deque()
        self.voice_client: Optional[discord.VoiceClient] = None
        self.current_song: Optional[Song] = None
        self.volume = initial_volume
        self.loop_mode = LoopMode.NONE
        self.auto_play_enabled = False
        self.play_next_song = asyncio.Event()
        self.now_playing_message: Optional[discord.Message] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.playback_start_time: Optional[datetime] = None
        self.pause_start_time: Optional[datetime] = None
        self.total_paused_duration: timedelta = timedelta(seconds=0)
        self.autoplay_history = deque(maxlen=20)
        self.autoplay_task: Optional[asyncio.Task] = None
        self.current_effect = "none"
        self.seek_time = 0
        self.consecutive_play_failures = 0
        self.is_tts_interrupting = False
        self.update_lock = asyncio.Lock()
        self.UI_UPDATE_COOLDOWN = 2.0
        self.last_update_time: float = 0.0
        self.ui_update_task: Optional[asyncio.Task] = None
        self.current_task: Optional[str] = None
        self.main_task = self.bot.loop.create_task(self.play_song_loop())
        self.progress_updater_task = self.bot.loop.create_task(self.update_progress_loop())
        logger.info(f"[{self.guild.name}] MusicState 생성됨 (초기 볼륨: {int(self.volume * 100)}%)")

    async def set_task(self, description: str):
        """플레이어 UI에 현재 작업 상태를 표시합니다."""
        self.current_task = description
        await self.schedule_ui_update()

    async def clear_task(self):
        """플레이어 UI의 작업 상태 표시를 지웁니다."""
        self.current_task = None
        await self.schedule_ui_update()

    def _normalize_title(self, title: str) -> str:
        """노래 제목에서 (MV), [Official Audio] 등 불필요한 부분을 제거하여 비교하기 쉽게 만듭니다."""
        if not title: return ""
        title = title.lower()
        title = re.sub(r'\([^)]*\)|\[[^]]*\]', '', title)
        keywords = ['mv', 'music video', 'official', 'audio', 'live', 'cover', 'lyrics', '가사', '공식', '커버', '라이브', 'lyric video']
        for keyword in keywords: title = title.replace(keyword, '')
        title = re.sub(r'\s*[-\s–\s—]\s*', ' ', title)
        title = re.sub(r'[^a-z0-9\s\uac00-\ud7a3]', '', title)
        return " ".join(title.split())

    def get_current_playback_time(self) -> int:
        """현재 곡의 재생 시간을 초 단위로 계산하여 반환합니다."""
        if not self.playback_start_time or not self.current_song: return 0
        base_elapsed = (discord.utils.utcnow() - self.playback_start_time).total_seconds()
        paused_duration = self.total_paused_duration.total_seconds()
        current_pause = (discord.utils.utcnow() - self.pause_start_time).total_seconds() if self.voice_client and self.voice_client.is_paused() and self.pause_start_time else 0
        actual_elapsed = base_elapsed - paused_duration - current_pause
        effective_elapsed = actual_elapsed * EFFECT_SPEED_FACTORS.get(self.current_effect, 1.0)
        return int(max(0, min(effective_elapsed, self.current_song.duration)))
        
    def cancel_autoplay_task(self):
        """진행 중인 자동 재생 작업을 취소합니다."""
        if self.autoplay_task and not self.autoplay_task.done():
            self.autoplay_task.cancel()
            self.autoplay_task = None

    async def _prefetch_autoplay_song(self, last_played_song: Song):
        """
        [수정된 자동 재생 로직]
        대기열이 비었을 때, 이전 곡을 기반으로 다음 곡을 자동으로 탐색하고 큐에 추가합니다.
        속도 개선을 위해 검색량을 줄이고 검색 로직을 단순화했습니다.
        """
        try:
            if not last_played_song: return
            
            # 1. 시드 곡 정보 준비
            last_title_normalized = self._normalize_title(last_played_song.title)
            if last_title_normalized: 
                self.autoplay_history.append({"title": last_title_normalized, "uploader": last_played_song.uploader})
            
            # 단조로움을 피하기 위해 가끔 이전 곡들 중에서 시드를 선택
            seed_song_info = random.choice(list(self.autoplay_history)[-5:]) if len(self.autoplay_history) > 1 and random.random() < 0.2 else {"title": last_title_normalized, "uploader": last_played_song.uploader}
            
            # 2. 검색어 단순화 및 검색량 조절 (핵심 최적화)
            # - 기존: 10개 검색, 아티스트/유사곡 전략 분리
            # - 변경: 5개만 검색하여 속도 향상, 아티스트+제목 통합 검색으로 일관성 확보
            search_query = f"ytsearch5:{seed_song_info['uploader']} {seed_song_info['title']}"
            logger.info(f"[{self.guild.name}] [Autoplay] 다음 곡 탐색 (검색어: '{search_query}')")
            
            # 3. 유튜브에서 정보 가져오기
            data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False, process=True))
            if not data or not data.get('entries'):
                logger.warning(f"[{self.guild.name}] [Autoplay] 탐색 결과 없음.")
                return

            # 4. 후보곡 필터링 (품질 유지를 위해 기존 로직 유지)
            potential_songs = []
            recent_titles = [s["title"] for s in self.autoplay_history]
            positive_keywords = ['official audio', 'lyrics', 'lyric video', '음원']
            negative_keywords = ['reaction', '해석', '드라마', '애니', '장면', '코멘터리', 'commentary', 'live', 'cover']

            for entry in data.get('entries', []):
                if not entry: continue
                entry_title_normalized = self._normalize_title(entry.get('title', ''))
                if not entry_title_normalized: continue
                
                is_too_similar = any(fuzz.ratio(entry_title_normalized, rt) > 85 for rt in recent_titles) if RAPIDFUZZ_AVAILABLE else entry_title_normalized in recent_titles
                if is_too_similar or not (90 < entry.get('duration', 0) < 600): 
                    continue
                
                score = sum([2 for kw in positive_keywords if kw in entry.get('title', '').lower()]) - sum([5 for kw in negative_keywords if kw in entry.get('title', '').lower()])
                if entry.get('uploader') == seed_song_info["uploader"]: 
                    score += 1
                
                if score >= 0:
                    entry['score'] = score
                    potential_songs.append(entry)
            logger.info(f"[{self.guild.name}] [Autoplay] 필터링 후 {len(potential_songs)}개의 후보 곡 발견.")

            # 5. 최종 곡 선정 및 대기열 추가
            if potential_songs:
                new_song_data = random.choices(potential_songs, weights=[s['score'] + 1 for s in potential_songs], k=1)[0]
                new_song_obj = Song(new_song_data, self.guild.get_member(self.bot.user.id) or self.bot.user)
                self.queue.append(new_song_obj)
                logger.info(f"[{self.guild.name}] [Autoplay] 다음 곡 선택: '{new_song_obj.title}' (점수: {new_song_data['score']})")
                
                # 즉시 재생이 필요하면 재생 루프를 깨웁니다.
                if self.voice_client and not (self.voice_client.is_playing() or self.voice_client.is_paused()):
                    self.play_next_song.set()

        except asyncio.CancelledError: 
            pass # 작업 취소는 정상적인 종료이므로 로그를 남기지 않음
        except Exception: 
            logger.error(f"[{self.guild.name}] [Autoplay] Prefetch 작업 중 오류 발생", exc_info=True)
        finally: 
            self.autoplay_task = None

    async def create_now_playing_embed(self) -> discord.Embed:
        """현재 음악 상태를 기반으로 플레이어 Embed 메시지를 생성합니다."""
        if not self.current_song and self.current_task:
            embed = discord.Embed(title="⚙️ 작업 처리 중...", description=self.current_task, color=0x36393F)
            if self.bot.user and self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)
            return embed

        if self.current_song:
            song = self.current_song
            embed = discord.Embed(title=song.title, color=BOT_EMBED_COLOR, url=song.webpage_url)
            if song.thumbnail: embed.set_thumbnail(url=song.thumbnail)
            
            total_m, total_s = divmod(song.duration, 60)
            elapsed_s = self.get_current_playback_time()
            elapsed_m, elapsed_s_display = divmod(elapsed_s, 60)
            
            progress = elapsed_s / song.duration if song.duration > 0 else 0
            bar = '▬' * int(15 * progress) + '🔘' + '▬' * (15 - int(15 * progress))
            status = "일시정지됨" if self.voice_client and self.voice_client.is_paused() else f"**`{song.uploader}`**"
            
            embed.description = f"{status}\n\n`{elapsed_m}:{elapsed_s_display:02d}` {bar} `{total_m}:{total_s:02d}`\n\n**요청**: {song.requester.mention}"
        else:
            embed = discord.Embed(title="재생 중인 음악 없음", color=0x36393F)
            embed.description = f"`/재생` 또는 `즐겨찾기` 버튼으로 노래를 추가해주세요."
            if self.bot.user and self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        # Footer 생성 (볼륨, 반복모드, 자동재생, 네트워크 상태 등)
        footer_parts = [ f"🔉 {int(self.volume * 100)}%", f"{LOOP_MODE_DATA[self.loop_mode][1]} {LOOP_MODE_DATA[self.loop_mode][0]}", "🎶 자동재생 ON" if self.auto_play_enabled else "🎶 자동재생 OFF" ]
        effect_text = f"🎧 효과: {self.current_effect.capitalize()}" if self.current_effect != "none" else "🎧 효과: 없음"
        next_song_info = (f"{self.queue[0].title[:30]}..." if len(self.queue[0].title) > 30 else self.queue[0].title) if self.queue else "없음"
        
        settings = await load_music_settings()
        avg, stdev = get_network_stats(settings, self.guild.id)
        if avg is not None and stdev is not None:
            color_emoji = "🟢" if stdev < 400 else "🟡" if stdev < 1000 else "🔴"
            network_stats = f"{color_emoji} 응답속도: {avg/1000:.1f}s (±{stdev/1000:.1f}s)"
        else:
            network_stats = "🌐 응답속도: 측정 중..."

        footer_text = f"{' • '.join(footer_parts)}\n{effect_text}\n다음 곡: {next_song_info}\n{network_stats}"
        
        if self.current_song and self.current_task:
            footer_text += f"\n\n⚙️ {self.current_task}"

        embed.set_footer(text=footer_text)
        return embed

    async def cleanup(self, leave=False):
        """음악 상태를 초기화하고 모든 작업을 정리합니다."""
        self.cancel_autoplay_task()
        if self.main_task: self.main_task.cancel()
        if self.progress_updater_task: self.progress_updater_task.cancel()
        self.current_song = None
        self.queue.clear()
        if self.voice_client:
            self.voice_client.stop()
            if leave:
                try: await self.voice_client.disconnect(force=True)
                except Exception as e: logger.warning(f"[{self.guild.name}] 음성 채널 퇴장 중 오류: {e}")
                self.voice_client = None
        if self.now_playing_message: await self.schedule_ui_update()
    
    async def schedule_ui_update(self):
        """
        잦은 UI 업데이트로 인한 API 제한을 피하기 위해 업데이트 요청을 스케줄링합니다.
        일정 시간(UI_UPDATE_COOLDOWN) 내에 여러 요청이 들어오면 마지막 요청만 처리합니다.
        """
        current_time = time.time()
        if self.ui_update_task and not self.ui_update_task.done(): self.ui_update_task.cancel()
        if current_time - self.last_update_time >= self.UI_UPDATE_COOLDOWN:
            self.bot.loop.create_task(self._execute_ui_update())
        else:
            delay = self.UI_UPDATE_COOLDOWN - (current_time - self.last_update_time)
            self.ui_update_task = self.bot.loop.create_task(self._delayed_ui_update(delay))

    async def _delayed_ui_update(self, delay: float):
        """지연된 UI 업데이트를 실행합니다."""
        try:
            await asyncio.sleep(delay)
            await self._execute_ui_update()
        except asyncio.CancelledError: pass
        finally: self.ui_update_task = None

    async def _execute_ui_update(self):
        """실제로 플레이어 Embed 메시지를 수정(edit)하는 함수입니다."""
        async with self.update_lock:
            try:
                embed = await self.create_now_playing_embed()
                view = MusicPlayerView(self.cog, self)
                if self.now_playing_message: await self.now_playing_message.edit(embed=embed, view=view)
                elif self.text_channel: self.now_playing_message = await self.text_channel.send(embed=embed, view=view)
                self.last_update_time = time.time()
            except discord.HTTPException as e:
                if e.status == 429: # API rate limit
                    logger.warning(f"[{self.guild.name}] UI 업데이트 중 API 호출 제한 발생. 5초 후 재시도.")
                    await asyncio.sleep(5)
                    self.bot.loop.create_task(self._execute_ui_update())
                else: logger.error(f"[{self.guild.name}] Now Playing 메시지 업데이트/전송 실패: {e}")
            except Exception as e: logger.error(f"[{self.guild.name}] Now Playing 메시지 처리 중 예기치 않은 오류: {e}")

    async def update_progress_loop(self):
        """10초마다 현재 재생 진행률 바를 업데이트하기 위한 루프입니다."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(10)
            if self.voice_client and self.current_song and not self.voice_client.is_paused():
                await self.schedule_ui_update()

    async def play_song_loop(self):
        """
        음악 재생의 핵심 로직을 담고 있는 메인 루프입니다.
        play_next_song 이벤트가 설정될 때까지 기다렸다가 다음 곡을 재생합니다.
        """
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await self.play_next_song.wait()
            self.play_next_song.clear()
            
            previous_song = self.current_song
            
            # 다음 곡 결정 (한 곡 반복, 큐, 일반 순서 등)
            next_song = self.current_song if self.loop_mode == LoopMode.SONG and self.current_song else self.queue.popleft() if self.queue else None
            self.current_song = next_song

            if not self.current_song:
                # 큐가 비었고 자동 재생이 켜져 있으면 다음 곡 탐색 시작
                if self.auto_play_enabled and previous_song and not self.autoplay_task:
                    self.autoplay_task = self.bot.loop.create_task(self._prefetch_autoplay_song(previous_song))
                if previous_song is not None: await self.schedule_ui_update()
                continue
            
            if self.current_song != previous_song:
                await self.schedule_ui_update()
                await self.cog.cleanup_channel_messages(self)
            
            try:
                # yt-dlp로 스트리밍 가능한 URL을 가져옵니다.
                data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(self.current_song.webpage_url, download=False))
                stream_url = data.get('url')
                if not stream_url:
                    if self.text_channel: await self.text_channel.send(f"❌ '{self.current_song.title}'을(를) 재생할 수 없습니다 (스트림 주소 오류).", delete_after=20)
                    self.handle_after_play(ValueError("스트림 URL을 찾을 수 없음"))
                    continue
                
                self.current_song.stream_url = stream_url
                
                # FFmpeg 옵션 설정 (오디오 효과, 탐색 시간 등)
                ffmpeg_options = {'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin -ss {self.seek_time}', 'options': '-vn'}
                effect_filter = AUDIO_EFFECTS.get(self.current_effect)
                if effect_filter: ffmpeg_options['options'] += f' -af "{effect_filter}"'
                
                # 오디오 소스를 생성하여 음성 클라이언트로 재생
                source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(stream_url, **ffmpeg_options), volume=self.volume)
                self.voice_client.play(source, after=lambda e: self.handle_after_play(e))
                
                # 재생 관련 상태 변수 초기화
                self.consecutive_play_failures = 0
                self.playback_start_time = discord.utils.utcnow() - timedelta(seconds=self.seek_time / EFFECT_SPEED_FACTORS.get(self.current_effect, 1.0))
                self.pause_start_time = None
                self.total_paused_duration = timedelta(seconds=0)
                self.seek_time = 0

            except Exception as e:
                self.consecutive_play_failures += 1
                logger.error(f"'{self.current_song.title}' 재생 중 오류 발생 (연속 실패: {self.consecutive_play_failures}회)", exc_info=True)
                if self.consecutive_play_failures >= 3:
                    if self.text_channel: await self.text_channel.send(f"🚨 **재생 오류**: '{self.current_song.title}' 곡을 재생하는 데 반복적으로 실패하여 대기열을 초기화합니다.", delete_after=30)
                    self.queue.clear()
                    self.current_song = None
                self.handle_after_play(e)
                continue
            
            # 전체 반복 모드일 경우, 현재 곡을 다시 큐의 맨 뒤에 추가
            if self.loop_mode == LoopMode.QUEUE and self.current_song:
                self.queue.append(self.current_song)

    def handle_after_play(self, error):
        """노래 재생이 끝나거나 오류로 중단되었을 때 호출되는 콜백 함수입니다."""
        if self.is_tts_interrupting: return # TTS가 재생 중일 때는 아무것도 하지 않음
        if error: logger.error(f"재생 후 콜백 오류: {error}")
        # 다음 곡 재생을 위해 메인 루프를 깨웁니다.
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)
