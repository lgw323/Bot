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

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logging.getLogger("MusicCog").warning("rapidfuzz 라이브러리를 찾을 수 없습니다.")

from .music_utils import (
    Song, LoopMode, LOOP_MODE_DATA,
    BOT_EMBED_COLOR, YTDL_OPTIONS,
    ytdl, load_music_settings, increment_play_count
    # get_network_stats 제거됨
)
from .music_ui import MusicPlayerView

logger = logging.getLogger("MusicCog")

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
        self.seek_time = 0
        self.consecutive_play_failures = 0
        self.is_tts_interrupting = False
        self.update_lock = asyncio.Lock()
        self.UI_UPDATE_COOLDOWN = 1.0 
        self.last_update_time: float = 0.0
        self.ui_update_task: Optional[asyncio.Task] = None
        self.current_task: Optional[str] = None
        self.main_task = self.bot.loop.create_task(self.play_song_loop())
        logger.info(f"[{self.guild.name}] MusicState 생성됨")

    async def set_task(self, description: str):
        self.current_task = description
        await self.schedule_ui_update()

    async def clear_task(self):
        self.current_task = None
        await self.schedule_ui_update()

    def _normalize_title(self, title: str) -> str:
        if not title: return ""
        title = title.lower()
        title = re.sub(r'\([^)]*\)|\[[^]]*\]', '', title)
        keywords = ['mv', 'music video', 'official', 'audio', 'live', 'cover', 'lyrics', '가사', '공식', '커버', '라이브', 'lyric video']
        for keyword in keywords: title = title.replace(keyword, '')
        title = re.sub(r'\s*[-\s–\s—]\s*', ' ', title)
        title = re.sub(r'[^a-z0-9\s\uac00-\ud7a3]', '', title)
        return " ".join(title.split())

    def get_current_playback_time(self) -> int:
        if not self.playback_start_time or not self.current_song: return 0
        base_elapsed = (discord.utils.utcnow() - self.playback_start_time).total_seconds()
        paused_duration = self.total_paused_duration.total_seconds()
        current_pause = (discord.utils.utcnow() - self.pause_start_time).total_seconds() if self.voice_client and self.voice_client.is_paused() and self.pause_start_time else 0
        actual_elapsed = base_elapsed - paused_duration - current_pause
        return int(max(0, min(actual_elapsed, self.current_song.duration)))
        
    def cancel_autoplay_task(self):
        if self.autoplay_task and not self.autoplay_task.done():
            self.autoplay_task.cancel()
            self.autoplay_task = None

    async def _prefetch_autoplay_song(self, last_played_song: Song):
        try:
            if not last_played_song: return
            
            last_title = self._normalize_title(last_played_song.title)
            last_uploader = last_played_song.uploader
            
            self.autoplay_history.append(last_title)

            search_query = ""
            strategy = "artist_digging"
            
            feat_match = re.search(r'(?i)(?:feat|ft|with)\.?\s+([^\(\)\[\]\-]+)', last_played_song.title)
            
            if feat_match and random.random() < 0.3:
                featured_artist = feat_match.group(1).strip()
                search_query = f"ytsearch10:{featured_artist}"
                strategy = f"feat_hop ({featured_artist})"
            else:
                search_query = f"ytsearch10:{last_uploader}"
                strategy = "artist_digging"

            logger.info(f"[{self.guild.name}] [Autoplay] 전략: {strategy} / 검색어: '{search_query}'")
            
            data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False, process=True))
            
            if not data or 'entries' not in data:
                return

            candidates = []
            for entry in data['entries']:
                if not entry: continue
                
                title = entry.get('title', '')
                normalized_title = self._normalize_title(title)
                
                if normalized_title in self.autoplay_history:
                    continue
                
                if RAPIDFUZZ_AVAILABLE:
                    similarity = fuzz.ratio(normalized_title, last_title)
                    if similarity > 70: 
                        continue
                else:
                    if last_title in normalized_title or normalized_title in last_title:
                        continue
                    # [개선] 문자열 매칭 시 단어 단위(regex) 교집합을 확인하여 유사도 판별 보강
                    last_words = set(last_title.split())
                    curr_words = set(normalized_title.split())
                    if last_words and curr_words:
                        overlap = len(last_words.intersection(curr_words))
                        if overlap / max(len(last_words), len(curr_words)) > 0.5:
                            continue
                
                if not (90 < entry.get('duration', 0) < 600):
                    continue

                candidates.append(entry)

            if candidates:
                selected_data = random.choice(candidates)
                new_song = Song(selected_data, self.guild.get_member(self.bot.user.id) or self.bot.user)
                
                self.queue.append(new_song)
                logger.info(f"[{self.guild.name}] [Autoplay] 다음 곡 결정: '{new_song.title}'")
                
                if self.voice_client and not (self.voice_client.is_playing() or self.voice_client.is_paused()):
                    self.play_next_song.set()

        except Exception:
            logger.error(f"[{self.guild.name}] [Autoplay] 오류 발생", exc_info=True)
        finally:
            self.autoplay_task = None

    async def create_now_playing_embed(self) -> discord.Embed:
        if not self.current_song and self.current_task:
            embed = discord.Embed(title="⚙️ [시스템 처리 중...]", description=f"```\n{self.current_task}\n```", color=0x36393F)
            if self.bot.user and self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)
            return embed

        if self.current_song:
            song = self.current_song
            # SF 테마 색상 (Cyan)
            embed = discord.Embed(title=f"**[ 💽 오디오_데이터_로드_완료 ]**", color=0x00FFFF, url=song.webpage_url)
            if song.thumbnail: embed.set_thumbnail(url=song.thumbnail)
            
            total_m, total_s = divmod(song.duration, 60)
            elapsed_s = self.get_current_playback_time()
            elapsed_m, elapsed_s_display = divmod(elapsed_s, 60)
            
            progress = elapsed_s / song.duration if song.duration > 0 else 0
            bar_length = 12
            filled_length = int(bar_length * progress)
            # SF 스타일 진행 바: [████▒▒▒▒▒▒]
            bar = '█' * filled_length + '▒' * (bar_length - filled_length)
            
            status_emoji = "▶"
            status_text = "출력 중..."
            time_flow_text = ""

            if self.voice_client and not self.voice_client.is_paused() and self.playback_start_time:
                adjusted_start_dt = self.playback_start_time + self.total_paused_duration
                adjusted_ts = int(adjusted_start_dt.timestamp())
                time_flow_text = f"<t:{adjusted_ts}:R>" 
            elif self.voice_client and self.voice_client.is_paused():
                status_emoji = "⏸"
                status_text = "일시 중단됨"
            elif not self.playback_start_time:
                status_emoji = "⏳"
                status_text = "준비 중..."

            # yaml 포맷을 사용하여 터미널 느낌 구현
            description = (
                f"```yaml\n"
                f"제  목 : {song.title[:25]}{'...' if len(song.title) > 25 else ''}\n"
                f"아티스트 : {song.uploader[:20]}{'...' if len(song.uploader) > 20 else ''}\n"
                f"상  태 : {status_emoji} {status_text}\n"
                f"버  퍼 : [{bar}] {int(progress * 100)}%\n"
                f"시  간 : {elapsed_m:02d}:{elapsed_s_display:02d} / {total_m:02d}:{total_s:02d}\n"
                f"```"
            )
            
            if time_flow_text:
                description += f"⏱️ **경과 시간**: {time_flow_text}\n"
            
            description += f"\n`📡 데이터_소스`: **YouTube 스트림**\n`👤 승인자`: {song.requester.mention}"

            embed.description = description
        else:
            embed = discord.Embed(title="**[ 💤 시스템 대기 모드 ]**", color=0x36393F)
            embed.description = f"```\n대기열이 비어있습니다.\n/재생 또는 [즐겨찾기]로 오디오 캡슐을 투입하세요.\n```"
            if self.bot.user and self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        # Footer 정보 구성
        footer_parts = [ f"🔉 볼륨: {int(self.volume * 100)}%" ]
        
        loop_text = "➡️ 반복 없음"
        if self.loop_mode == LoopMode.SONG: loop_text = "🔂 한 곡 반복"
        elif self.loop_mode == LoopMode.QUEUE: loop_text = "🔁 전체 반복"
        footer_parts.append(loop_text)
        
        footer_parts.append("🤖 자동재생 ON" if self.auto_play_enabled else "🤖 자동재생 OFF")
        
        next_song_info = (f"{self.queue[0].title[:20]}..." if len(self.queue[0].title) > 20 else self.queue[0].title) if self.queue else "없음"
        
        # [수정] 네트워크 레이턴시 표시 부분 제거
        footer_text = f"{' | '.join(footer_parts)}\n다음 트랙: {next_song_info}"
        
        if self.current_song and self.current_task:
            footer_text += f"\n\n⚙️ [백그라운드 작업]: {self.current_task}"

        embed.set_footer(text=footer_text)
        return embed

    async def cleanup(self, leave=False):
        self.cancel_autoplay_task()
        if self.main_task: self.main_task.cancel()
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
        if self.ui_update_task and not self.ui_update_task.done():
            self.ui_update_task.cancel()

        self.ui_update_task = self.bot.loop.create_task(self._delayed_ui_update())

    async def _delayed_ui_update(self):
        try:
            await asyncio.sleep(self.UI_UPDATE_COOLDOWN)
            async with self.update_lock:
                await self._execute_ui_update()
        except asyncio.CancelledError:
            pass

    async def _execute_ui_update(self):
        try:
            from .music_utils import get_top_played_songs
            embed = await self.create_now_playing_embed()
            top_songs = await get_top_played_songs(self.guild.id, limit=5)
            view = MusicPlayerView(self.cog, self, top_songs)
            if self.now_playing_message:
                await self.now_playing_message.edit(embed=embed, view=view)
            elif self.text_channel:
                self.now_playing_message = await self.text_channel.send(embed=embed, view=view)
            self.last_update_time = time.time()
        except discord.HTTPException as e:
            if e.status != 429:
                logger.error(f"[{self.guild.name}] Now Playing 메시지 업데이트/전송 실패: {e}")
        except Exception as e:
            logger.error(f"[{self.guild.name}] Now Playing 메시지 처리 중 예기치 않은 오류: {e}", exc_info=True)

    async def play_song_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await self.play_next_song.wait()
            self.play_next_song.clear()
            
            previous_song = self.current_song
            
            next_song = self.current_song if self.loop_mode == LoopMode.SONG and self.current_song else self.queue.popleft() if self.queue else None
            self.current_song = next_song

            if not self.current_song:
                if self.auto_play_enabled and previous_song and not self.autoplay_task:
                    self.autoplay_task = self.bot.loop.create_task(self._prefetch_autoplay_song(previous_song))
                if previous_song is not None: await self.schedule_ui_update()
                continue
            
            if self.current_song != previous_song:
                await self.schedule_ui_update()
                await self.cog.cleanup_channel_messages(self)
            
            try:
                data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(self.current_song.webpage_url, download=False))
                stream_url = data.get('url')
                if not stream_url:
                    if self.text_channel: await self.text_channel.send(f"❌ '{self.current_song.title}'을(를) 재생할 수 없습니다.", delete_after=20)
                    self.handle_after_play(ValueError("스트림 URL을 찾을 수 없음"))
                    continue
                
                self.current_song.stream_url = stream_url
                
                ffmpeg_options = {'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin -ss {self.seek_time}', 'options': '-vn'}
                
                source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(stream_url, **ffmpeg_options), volume=self.volume)
                
                # [오류 방지] 이미 재생 중인 경우 ClientException 발생 방지
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                    
                self.voice_client.play(source, after=lambda e: self.handle_after_play(e))
                
                if self.current_song.webpage_url:
                    self.bot.loop.create_task(increment_play_count(self.guild.id, self.current_song.webpage_url, self.current_song.title))
                
                self.consecutive_play_failures = 0
                self.playback_start_time = discord.utils.utcnow() - timedelta(seconds=self.seek_time)
                self.pause_start_time = None
                self.total_paused_duration = timedelta(seconds=0)
                self.seek_time = 0
                
                await self.schedule_ui_update()

            except Exception as e:
                self.consecutive_play_failures += 1
                logger.error(f"'{self.current_song.title}' 재생 중 오류 발생", exc_info=True)
                if self.consecutive_play_failures >= 3:
                    if self.text_channel: await self.text_channel.send(f"🚨 **재생 오류**: '{self.current_song.title}' 곡을 재생하는 데 반복적으로 실패하여 대기열을 초기화합니다.", delete_after=30)
                    self.queue.clear()
                    self.current_song = None
                self.handle_after_play(e)
                continue
            
            if self.loop_mode == LoopMode.QUEUE and self.current_song:
                self.queue.append(self.current_song)

    def handle_after_play(self, error):
        if self.is_tts_interrupting: return
        if error: logger.error(f"재생 후 콜백 오류: {error}")
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)