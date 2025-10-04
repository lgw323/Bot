import asyncio
import logging
import random
import re
from collections import deque
from typing import Optional, List
from datetime import datetime, timedelta
import time # 추가: 마지막 업데이트 시간을 추적하기 위해 time 모듈을 임포트합니다.

import discord
from discord.ext import commands
import yt_dlp

# --- 모듈화된 파일에서 클래스와 함수 임포트 (경로 수정) ---
from .music_utils import (
    Song, LoopMode, LOOP_MODE_DATA,
    BOT_EMBED_COLOR, YTDL_OPTIONS,
    ytdl
)
from .music_ui import MusicPlayerView

logger = logging.getLogger("MusicCog")

# --- 오디오 이펙트 FFmpeg 필터 정의 ---
AUDIO_EFFECTS = {
    "none": "",
    "bassboost": "bass=g=15",
    "speedup": "rubberband=tempo=1.25",
    "nightcore": "atempo=1.2,asetrate=48000*1.2",
    "vaporwave": "atempo=0.8,asetrate=48000*0.85"
}

EFFECT_SPEED_FACTORS = {
    "speedup": 1.25,
    "nightcore": 1.2,
    "vaporwave": 0.8,
}

# --- 상태 관리 클래스 ---
class MusicState:
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
        
        # --- 지능형 UI 업데이트를 위한 상태 변수 ---
        self.UI_UPDATE_COOLDOWN = 2.0  # API 호출 후 최소 대기 시간 (초)
        self.last_update_time: float = 0.0 # 마지막 업데이트 성공 시간
        self.ui_update_task: Optional[asyncio.Task] = None # 예약된 업데이트 작업

        self.main_task = self.bot.loop.create_task(self.play_song_loop())
        self.progress_updater_task = self.bot.loop.create_task(self.update_progress_loop())
        logger.info(f"[{self.guild.name}] MusicState 생성됨 (초기 볼륨: {int(self.volume * 100)}%)")

    def _normalize_title(self, title: str) -> str:
        """노래 제목에서 버전 정보, 특수문자 등을 제거하여 정규화합니다."""
        if not title:
            return ""
        title = title.lower()
        title = re.sub(r'\([^)]*\)', '', title)
        title = re.sub(r'\[[^]]*\]', '', title)
        keywords = ['mv', 'music video', 'official', 'audio', 'live', 'cover', 'lyrics', '가사', '공식', '커버', '라이브']
        for keyword in keywords:
            title = title.replace(keyword, '')
        title = re.sub(r'[^a-z0-9\s\uac00-\ud7a3]', '', title)
        return " ".join(title.split())

    def get_current_playback_time(self) -> int:
        if not self.playback_start_time or not self.current_song:
            return 0
        
        base_elapsed = (discord.utils.utcnow() - self.playback_start_time).total_seconds()
        paused_duration = self.total_paused_duration.total_seconds()
        
        current_pause = 0
        if self.voice_client and self.voice_client.is_paused() and self.pause_start_time:
            current_pause = (discord.utils.utcnow() - self.pause_start_time).total_seconds()
            
        actual_elapsed = base_elapsed - paused_duration - current_pause
        speed_factor = EFFECT_SPEED_FACTORS.get(self.current_effect, 1.0)
        effective_elapsed = actual_elapsed * speed_factor

        return int(max(0, min(effective_elapsed, self.current_song.duration)))
        
    def cancel_autoplay_task(self):
        if self.autoplay_task and not self.autoplay_task.done():
            self.autoplay_task.cancel()
            self.autoplay_task = None

    async def _prefetch_autoplay_song(self, last_played_song: Song):
        try:
            if not last_played_song: return
            
            normalized_title = self._normalize_title(last_played_song.title)
            if normalized_title:
                self.autoplay_history.append(normalized_title)

            logger.info(f"[{self.guild.name}] [Autoplay] '{last_played_song.title}' 기반으로 다음 곡 탐색 시작.")
            
            ytdl_opts = YTDL_OPTIONS.copy()
            ytdl_opts.update({'playliststart': 2, 'playlistend': 20, 'noplaylist': False})

            with yt_dlp.YoutubeDL(ytdl_opts) as ydl_prefetch:
                future = self.bot.loop.run_in_executor(None, lambda: ydl_prefetch.extract_info(last_played_song.webpage_url, download=False))
                data = await asyncio.wait_for(future, timeout=30.0)

            if not data or not data.get('entries'):
                logger.warning(f"[{self.guild.name}] [Autoplay] 탐색 결과, 추천 곡을 찾지 못했습니다.")
                return

            recent_titles = set(list(self.autoplay_history)[-5:])

            potential_songs = []
            for entry in data.get('entries', []):
                if not entry: continue
                
                entry_title = entry.get('title')
                normalized_entry_title = self._normalize_title(entry_title)
                
                if not normalized_entry_title or normalized_entry_title in recent_titles:
                    continue
                if not (60 < entry.get('duration', 0) < 900):
                    continue
                
                potential_songs.append(entry)

            logger.info(f"[{self.guild.name}] [Autoplay] 필터링 후 {len(potential_songs)}개의 후보 곡 발견.")

            if potential_songs:
                new_song_data = random.choice(potential_songs)
                bot_member = self.guild.get_member(self.bot.user.id) or self.bot.user
                new_song_obj = Song(new_song_data, bot_member)
                self.queue.append(new_song_obj)
                
                final_normalized_title = self._normalize_title(new_song_obj.title)
                if final_normalized_title:
                    self.autoplay_history.append(final_normalized_title)

                logger.info(f"[{self.guild.name}] [Autoplay] 다음 곡 선택: '{new_song_obj.title}' (대기열에 추가됨)")
                
                if self.voice_client and not (self.voice_client.is_playing() or self.voice_client.is_paused()):
                    self.play_next_song.set()
            else:
                logger.info(f"[{self.guild.name}] [Autoplay] 재생 기록 필터링 후 남은 후보 곡이 없습니다.")

        except asyncio.TimeoutError:
            logger.warning(f"[{self.guild.name}] [Autoplay] 다음 곡 검색 작업 시간 초과.")
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error(f"[{self.guild.name}] [Autoplay] Prefetch 작업 중 오류 발생", exc_info=True)
        finally:
            self.autoplay_task = None

    def create_now_playing_embed(self) -> discord.Embed:
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

        footer_parts = [
            f"🔉 {int(self.volume * 100)}%",
            f"{LOOP_MODE_DATA[self.loop_mode][1]} {LOOP_MODE_DATA[self.loop_mode][0]}",
            "🎶 자동재생 ON" if self.auto_play_enabled else "🎶 자동재생 OFF"
        ]
        effect_text = f"🎧 효과: {self.current_effect.capitalize()}" if self.current_effect != "none" else "🎧 효과: 없음"
        
        next_song_info = "없음"
        if self.queue:
            next_song_info = f"{self.queue[0].title[:30]}..." if len(self.queue[0].title) > 30 else self.queue[0].title

        embed.set_footer(text=f"{' • '.join(footer_parts)}\n{effect_text}\n다음 곡: {next_song_info}")
        return embed

    async def cleanup(self, leave=False):
        self.cancel_autoplay_task()
        if self.main_task: self.main_task.cancel()
        if self.progress_updater_task: self.progress_updater_task.cancel()
        
        self.current_song = None
        self.queue.clear()
        
        if self.voice_client:
            self.voice_client.stop()
            if leave:
                try:
                    await self.voice_client.disconnect(force=True)
                except Exception as e:
                    logger.warning(f"[{self.guild.name}] 음성 채널 퇴장 중 오류: {e}")
                self.voice_client = None

        if self.now_playing_message:
            # cleanup 시에도 스케줄러를 통해 안전하게 UI 업데이트
            await self.schedule_ui_update()
    
    async def schedule_ui_update(self):
        """지능형 UI 업데이트 스케줄러. API 호출을 최소화합니다."""
        current_time = time.time()
        time_since_last_update = current_time - self.last_update_time

        # 이미 예약된 업데이트가 있다면 취소 (최신 요청만 처리)
        if self.ui_update_task and not self.ui_update_task.done():
            self.ui_update_task.cancel()

        if time_since_last_update >= self.UI_UPDATE_COOLDOWN:
            # 쿨타임이 지났으면 즉시 업데이트 실행
            self.bot.loop.create_task(self._execute_ui_update())
        else:
            # 쿨타임 중이면, 남은 시간만큼 기다렸다가 업데이트하도록 예약
            delay = self.UI_UPDATE_COOLDOWN - time_since_last_update
            self.ui_update_task = self.bot.loop.create_task(self._delayed_ui_update(delay))

    async def _delayed_ui_update(self, delay: float):
        """예약된 UI 업데이트를 실행하는 내부 함수."""
        try:
            await asyncio.sleep(delay)
            await self._execute_ui_update()
        except asyncio.CancelledError:
            # 최신 요청에 의해 작업이 취소된 경우
            pass
        finally:
            self.ui_update_task = None

    async def _execute_ui_update(self):
        """실제로 Discord API를 호출하여 메시지를 수정하는 함수."""
        async with self.update_lock:
            try:
                embed = self.create_now_playing_embed()
                view = MusicPlayerView(self.cog, self)
                if self.now_playing_message:
                    await self.now_playing_message.edit(embed=embed, view=view)
                elif self.text_channel:
                    self.now_playing_message = await self.text_channel.send(embed=embed, view=view)
                
                # 성공적으로 API를 호출했으므로, 마지막 업데이트 시간 기록
                self.last_update_time = time.time()
            except discord.HTTPException as e:
                if e.status == 429: # Rate Limit
                    logger.warning(f"[{self.guild.name}] UI 업데이트 중 API 호출 제한에 걸렸습니다. 5초 후 재시도합니다.")
                    await asyncio.sleep(5)
                    self.bot.loop.create_task(self._execute_ui_update()) # 재시도
                else:
                    logger.error(f"[{self.guild.name}] Now Playing 메시지 업데이트/전송 실패: {e}")
            except Exception as e:
                 logger.error(f"[{self.guild.name}] Now Playing 메시지 처리 중 예기치 않은 오류: {e}")

    async def update_progress_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(10)
            if self.voice_client and self.current_song and not self.voice_client.is_paused():
                await self.schedule_ui_update() # 기존 update_now_playing_message()를 스케줄러 호출로 변경

    async def play_song_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await self.play_next_song.wait()
            self.play_next_song.clear()
            
            previous_song = self.current_song
            
            next_song = None
            if self.loop_mode == LoopMode.SONG and self.current_song:
                next_song = self.current_song
            elif self.queue:
                next_song = self.queue.popleft()
            
            self.current_song = next_song

            if not self.current_song:
                if self.auto_play_enabled and previous_song and not self.autoplay_task:
                    self.autoplay_task = self.bot.loop.create_task(self._prefetch_autoplay_song(previous_song))

                if previous_song is not None:
                    await self.schedule_ui_update() # 기존 update_now_playing_message()를 스케줄러 호출로 변경
                continue

            if self.current_song != previous_song:
                await self.schedule_ui_update() # 기존 update_now_playing_message()를 스케줄러 호출로 변경
                await self.cog.cleanup_channel_messages(self)
            
            try:
                data = await self.bot.loop.run_in_executor(
                    None, 
                    lambda: ytdl.extract_info(self.current_song.webpage_url, download=False)
                )
                stream_url = data.get('url')

                if not stream_url:
                    logger.error(f"[{self.guild.name}] '{self.current_song.title}'의 스트림 URL을 얻지 못했습니다.")
                    if self.text_channel:
                        await self.text_channel.send(f"❌ '{self.current_song.title}'을(를) 재생할 수 없습니다 (스트림 주소 오류).", delete_after=20)
                    self.handle_after_play(ValueError("스트림 URL을 찾을 수 없음"))
                    continue
                
                self.current_song.stream_url = stream_url
                
                ffmpeg_options = {'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin -ss {self.seek_time}', 'options': '-vn'}
                effect_filter = AUDIO_EFFECTS.get(self.current_effect)
                if effect_filter:
                    ffmpeg_options['options'] += f' -af "{effect_filter}"'
                
                source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_options)
                volume_source = discord.PCMVolumeTransformer(source, volume=self.volume)
                self.voice_client.play(volume_source, after=lambda e: self.handle_after_play(e))
                
                self.consecutive_play_failures = 0
                self.playback_start_time = discord.utils.utcnow() - timedelta(seconds=self.seek_time / EFFECT_SPEED_FACTORS.get(self.current_effect, 1.0))
                self.pause_start_time = None
                self.total_paused_duration = timedelta(seconds=0)
                self.seek_time = 0

            except Exception as e:
                self.consecutive_play_failures += 1
                logger.error(f"'{self.current_song.title}' 재생 중 오류 발생 (연속 실패: {self.consecutive_play_failures}회)", exc_info=True)

                if self.consecutive_play_failures >= 3:
                    if self.text_channel:
                        await self.text_channel.send(f"🚨 **재생 오류**: '{self.current_song.title}' 곡을 재생하는 데 반복적으로 실패하여 대기열을 초기화합니다.", delete_after=30)
                    self.queue.clear()
                    self.current_song = None
                
                self.handle_after_play(e)
                continue
            
            if self.loop_mode == LoopMode.QUEUE and self.current_song:
                self.queue.append(self.current_song)

    def handle_after_play(self, error):
        if self.is_tts_interrupting:
            return

        if error:
            logger.error(f"재생 후 콜백 오류: {error}")
        
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)
