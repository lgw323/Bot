import asyncio
import io
import logging
import random
import re
import subprocess
import threading
from collections import deque
from typing import Optional
from datetime import datetime, timedelta
import time

import discord
from discord.ext import commands

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logging.getLogger(__name__).warning("rapidfuzz 라이브러리를 찾을 수 없습니다.")

from .music_utils import (
    Song, LoopMode,
    increment_play_count,
)
from .music_playback import (
    PlaybackBackend,
    PlaybackPreparationCancelled,
    create_playback_backend,
)
from .music_ui import MusicPlayerView

logger: logging.Logger = logging.getLogger(__name__)


class FFmpegStderrCapture(io.RawIOBase):
    """Keep a small sanitized tail of FFmpeg diagnostics for callbacks."""

    def __init__(self, max_bytes: int = 8192) -> None:
        super().__init__()
        self.max_bytes = max_bytes
        self._buffer = bytearray()
        self._lock = threading.Lock()

    def writable(self) -> bool:
        return True

    def write(self, data: bytes | bytearray) -> int:
        chunk = bytes(data)
        with self._lock:
            self._buffer.extend(chunk)
            if len(self._buffer) > self.max_bytes:
                del self._buffer[:-self.max_bytes]
        return len(chunk)

    def summary(self) -> str:
        with self._lock:
            text = bytes(self._buffer).decode("utf-8", errors="replace")

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        important = [
            line
            for line in lines
            if any(
                marker in line.lower()
                for marker in ("403", "forbidden", "error", "failed")
            )
        ]
        selected = important[-4:] if important else lines[-2:]
        summary = " | ".join(selected)
        summary = re.sub(r"https?://\S+", "[URL 생략]", summary)
        return summary[:800]


class ErrorAwarePCMVolumeTransformer(discord.PCMVolumeTransformer):
    """Expose the wrapped FFmpeg failure to discord.py's audio player."""

    FFMPEG_EXIT_WAIT_SECONDS = 1.0

    def read(self) -> bytes:
        data = super().read()
        if data or self._current_error is not None:
            return data

        source = self.original
        if getattr(source, "_stopped", False):
            return data

        process = getattr(source, "_process", None)
        wait = getattr(process, "wait", None)
        if not callable(wait):
            return data

        try:
            return_code = wait(timeout=self.FFMPEG_EXIT_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            source._current_error = RuntimeError(  # type: ignore[attr-defined]
                "FFmpeg output ended but the process did not exit within "
                f"{self.FFMPEG_EXIT_WAIT_SECONDS:.1f}s"
            )
        except Exception as error:
            source._current_error = RuntimeError(  # type: ignore[attr-defined]
                f"Failed to read FFmpeg exit status: {error}"
            )
        else:
            if return_code != 0:
                source._current_error = RuntimeError(  # type: ignore[attr-defined]
                    f"FFmpeg exited with code {return_code}"
                )

        return data

    @property
    def _current_error(self) -> Optional[Exception]:
        return getattr(self.original, "_current_error", None)


class MusicState:
    PLAYBACK_RETRY_DELAYS = (3.0, 8.0)

    def __init__(
        self,
        bot: commands.Bot,
        cog: commands.Cog,
        guild: discord.Guild,
        initial_volume: float = 0.5,
        playback_backend: Optional[PlaybackBackend] = None,
    ) -> None:
        self.bot: commands.Bot = bot
        self.cog: commands.Cog = cog
        self.guild: discord.Guild = guild
        self.queue: deque = deque()
        self.voice_client: Optional[discord.VoiceClient] = None
        self.current_song: Optional[Song] = None
        self.volume: float = initial_volume
        self.loop_mode: LoopMode = LoopMode.NONE
        self.auto_play_enabled: bool = False
        self.play_next_song: asyncio.Event = asyncio.Event()
        self.now_playing_message: Optional[discord.Message] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.playback_start_time: Optional[datetime] = None
        self.pause_start_time: Optional[datetime] = None
        self.total_paused_duration: timedelta = timedelta(seconds=0)
        self.autoplay_history: deque = deque(maxlen=20)
        self.autoplay_task: Optional[asyncio.Task] = None
        self.seek_time: int = 0
        self.consecutive_play_failures: int = 0
        self.playback_retry_song: Optional[Song] = None
        self.playback_retry_not_before: float = 0.0
        self.playback_retry_cancelled: asyncio.Event = asyncio.Event()
        self.playback_backend = playback_backend or create_playback_backend(
            guild.id
        )
        self.preparing_song: Optional[Song] = None
        self.preparation_skipped_song: Optional[Song] = None
        self.ffmpeg_stderr: Optional[FFmpegStderrCapture] = None
        self.is_tts_interrupting: bool = False
        self.update_lock: asyncio.Lock = asyncio.Lock()
        self.UI_UPDATE_COOLDOWN: float = 3.0
        self.last_update_time: float = 0.0
        self.ui_update_task: Optional[asyncio.Task] = None
        self._ui_update_requested: bool = False
        self.current_task: Optional[str] = None
        self.main_task: Optional[asyncio.Task] = self.bot.loop.create_task(
            self.play_song_loop()
        )
        logger.info(f"[{self.guild.name}] MusicState 생성됨")

    async def set_task(self, description: str) -> None:
        self.current_task = description
        await self.schedule_ui_update()

    async def clear_task(self) -> None:
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
        
    async def _prefetch_autoplay_song(self, last_played_song: Song) -> None:
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
            
            try:
                data = await self.bot.loop.run_in_executor(
                    None,
                    lambda: extract_ytdlp_info(
                        search_query,
                        download=False,
                        process=True,
                    ),
                )
            except Exception as e:
                logger.warning(f"[{self.guild.name}] [Autoplay] 검색 중 영상을 불러올 수 없습니다 (삭제/비공개 됨): {e}")
                return
            
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
                guild_member = self.guild.get_member(self.bot.user.id) if self.bot.user else None
                requester = guild_member or self.guild.me
                new_song = Song(selected_data, requester)
                
                self.queue.append(new_song)
                logger.info(f"[{self.guild.name}] [Autoplay] 다음 곡 결정: '{new_song.title}'")
                
                if self.voice_client and not (self.voice_client.is_playing() or self.voice_client.is_paused()):
                    self.play_next_song.set()

        except Exception:
            logger.error(f"[{self.guild.name}] [Autoplay] 오류 발생", exc_info=True)
        finally:
            current_task = asyncio.current_task()
            if self.autoplay_task is current_task:
                self.autoplay_task = None

    def cancel_autoplay_task(self) -> None:
        """Cancel only the pending autoplay lookup, if one exists."""
        task = self.autoplay_task
        if task is None:
            return

        if not task.done():
            task.cancel()

        if self.autoplay_task is task:
            self.autoplay_task = None

    async def create_now_playing_embed(self) -> discord.Embed:
        if not self.current_song and self.current_task:
            embed = discord.Embed(title="⚙️ [시스템 처리 중...]", description=f"```\n{self.current_task}\n```", color=0x36393F)
            if self.bot.user and self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)
            return embed

        if self.current_song:
            song = self.current_song
            embed = discord.Embed(title=f"**[ 💽 오디오_데이터_로드_완료 ]**", color=0x00FFFF, url=song.webpage_url)
            if song.thumbnail: embed.set_thumbnail(url=song.thumbnail)
            
            total_m, total_s = divmod(song.duration, 60)
            elapsed_s = self.get_current_playback_time()
            elapsed_m, elapsed_s_display = divmod(elapsed_s, 60)
            
            progress = elapsed_s / song.duration if song.duration > 0 else 0
            bar_length = 12
            filled_length = int(bar_length * progress)
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
        
        footer_parts = [ f"🔉 볼륨: {int(self.volume * 100)}%" ]
        
        loop_text = "➡️ 반복 없음"
        if self.loop_mode == LoopMode.SONG: loop_text = "🔂 한 곡 반복"
        elif self.loop_mode == LoopMode.QUEUE: loop_text = "🔁 전체 반복"
        footer_parts.append(loop_text)
        
        footer_parts.append("🤖 자동재생 ON" if self.auto_play_enabled else "🤖 자동재생 OFF")
        
        next_song_info = (f"{self.queue[0].title[:20]}..." if len(self.queue[0].title) > 20 else self.queue[0].title) if self.queue else "없음"
        
        footer_text = f"{' | '.join(footer_parts)}\n다음 트랙: {next_song_info}"
        
        if self.current_song and self.current_task:
            footer_text += f"\n\n⚙️ [백그라운드 작업]: {self.current_task}"

        embed.set_footer(text=footer_text)
        return embed

    async def _stop_background_tasks(self) -> None:
        tasks_to_stop = [
            task
            for task in (
                self.main_task,
                self.autoplay_task,
                self.ui_update_task,
            )
            if task is not None and not task.done()
        ]
        for task in tasks_to_stop:
            task.cancel()
        if tasks_to_stop:
            await asyncio.gather(*tasks_to_stop, return_exceptions=True)

        self.main_task = None
        self.autoplay_task = None
        self.ui_update_task = None
        self._ui_update_requested = False

    async def cleanup(
        self,
        leave: bool = False,
        update_ui: bool = True,
    ) -> None:
        await self._stop_background_tasks()
        self._clear_playback_retry()
        self.playback_retry_cancelled.clear()
        self.consecutive_play_failures = 0
        self.current_song = None
        self.queue.clear()
        if self.voice_client:
            self.voice_client.stop()
            if leave:
                try: await self.voice_client.disconnect(force=True)
                except Exception as e: logger.warning(f"[{self.guild.name}] 음성 채널 퇴장 중 오류: {e}")
                self.voice_client = None
        await self.playback_backend.close()
        if self.now_playing_message and update_ui:
            await self.schedule_ui_update()
    
    async def schedule_ui_update(self) -> None:
        self._ui_update_requested = True
        if self.ui_update_task and not self.ui_update_task.done():
            return

        self.ui_update_task = self.bot.loop.create_task(self._delayed_ui_update())

    async def _delayed_ui_update(self) -> None:
        try:
            while self._ui_update_requested:
                self._ui_update_requested = False
                elapsed = time.monotonic() - self.last_update_time
                delay = max(0.0, self.UI_UPDATE_COOLDOWN - elapsed)
                if delay:
                    await asyncio.sleep(delay)
                async with self.update_lock:
                    await self._execute_ui_update()
        except asyncio.CancelledError:
            raise
        finally:
            if self.ui_update_task is asyncio.current_task():
                self.ui_update_task = None

    async def _execute_ui_update(self) -> None:
        try:
            from .music_utils import get_top_played_songs
            embed = await self.create_now_playing_embed()
            top_songs = await get_top_played_songs(self.guild.id, limit=5)
            view = MusicPlayerView(self.cog, self, top_songs)
            if self.now_playing_message:
                await self.now_playing_message.edit(embed=embed, view=view)
            elif self.text_channel:
                self.now_playing_message = await self.text_channel.send(embed=embed, view=view)
        except discord.HTTPException as e:
            if e.status != 429:
                logger.error(f"[{self.guild.name}] Now Playing 메시지 업데이트/전송 실패: {e}")
        except Exception as e:
            logger.error(f"[{self.guild.name}] Now Playing 메시지 처리 중 예기치 않은 오류: {e}", exc_info=True)
        finally:
            self.last_update_time = time.monotonic()

    def _clear_playback_retry(self) -> None:
        self.playback_retry_song = None
        self.playback_retry_not_before = 0.0
        if self.current_task and self.current_task.startswith("🔄 음악 스트림"):
            self.current_task = None

    async def _wait_for_playback_retry(self, song: Song) -> bool:
        if self.playback_retry_song is not song:
            return True

        remaining = max(
            0.0,
            self.playback_retry_not_before - time.monotonic(),
        )
        if remaining:
            try:
                await asyncio.wait_for(
                    self.playback_retry_cancelled.wait(),
                    timeout=remaining,
                )
            except TimeoutError:
                pass
            else:
                return False

        if self.playback_retry_song is not song:
            return False

        self._clear_playback_retry()
        self.playback_retry_cancelled.clear()
        await self.schedule_ui_update()
        return True

    def cancel_pending_playback_retry(self) -> bool:
        song = self.playback_retry_song
        if song is None:
            return False

        self._remove_song_from_queue(song)
        if self.current_song is song:
            self.current_song = None
        self.consecutive_play_failures = 0
        self._clear_playback_retry()
        self.playback_retry_cancelled.set()
        self.play_next_song.set()
        return True

    def cancel_active_preparation(self) -> bool:
        song = self.preparing_song
        if song is None:
            return False
        self.preparation_skipped_song = song
        self.playback_backend.cancel_current()
        return True

    def _select_next_song(self) -> Optional[Song]:
        if self.playback_retry_song is not None:
            retry_song = self.playback_retry_song
            self._remove_song_from_queue(retry_song)
            return retry_song
        if self.loop_mode == LoopMode.SONG and self.current_song:
            return self.current_song
        return self.queue.popleft() if self.queue else None

    async def play_song_loop(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await self.play_next_song.wait()
            self.play_next_song.clear()
            
            # 음성 채널이 끊긴 경우 재연결 대기
            if not self.voice_client or not self.voice_client.is_connected():
                reconnect_wait = 0
                while self.voice_client and not self.voice_client.is_connected() and reconnect_wait < 10:
                    await asyncio.sleep(1.0)
                    reconnect_wait += 1

                # 대기 후에도 연결되지 않았다면 대기열 복구 후 루프 양보
                if not self.voice_client or not self.voice_client.is_connected():
                    logger.warning(f"[{self.guild.name}] 음성 채널이 연결되어 있지 않아 재생을 일시 정지하고 대기를 시작합니다.")
                    if self.current_song:
                        self.queue.appendleft(self.current_song)
                        self.current_song = None
                    await asyncio.sleep(5.0)
                    self.play_next_song.set()
                    continue

            previous_song = self.current_song
            self.current_song = self._select_next_song()

            if not self.current_song:
                if self.auto_play_enabled and previous_song and not self.autoplay_task:
                    self.autoplay_task = self.bot.loop.create_task(self._prefetch_autoplay_song(previous_song))
                if previous_song is not None: await self.schedule_ui_update()
                continue

            if not await self._wait_for_playback_retry(self.current_song):
                continue
            
            if self.current_song != previous_song:
                await self.schedule_ui_update()
                await self.cog.cleanup_channel_messages(self)
            
            try:
                self.preparing_song = self.current_song
                await self.set_task("⬇️ 음악을 안전하게 준비하는 중...")
                prepared = await self.playback_backend.prepare(
                    self.current_song,
                    self.seek_time,
                )
                if self.preparation_skipped_song is self.current_song:
                    self.current_song = None
                    self.preparation_skipped_song = None
                    self.consecutive_play_failures = 0
                    self.play_next_song.set()
                    continue

                self.current_song.stream_url = prepared.stream_url
                self.ffmpeg_stderr = FFmpegStderrCapture()
                ffmpeg_source = discord.FFmpegPCMAudio(
                    prepared.source,
                    stderr=self.ffmpeg_stderr,
                    before_options=prepared.before_options,
                    options=prepared.options,
                )
                source = ErrorAwarePCMVolumeTransformer(
                    ffmpeg_source,
                    volume=self.volume,
                )
                
                if self.voice_client and self.voice_client.is_playing():
                    self.voice_client.stop()
                    
                if self.voice_client:
                    self.voice_client.play(source, after=lambda e: self.handle_after_play(e))
                
                if self.current_song.webpage_url:
                    self.bot.loop.create_task(increment_play_count(self.guild.id, self.current_song.webpage_url, self.current_song.title))
                
                self.playback_start_time = discord.utils.utcnow() - timedelta(seconds=self.seek_time)
                self.pause_start_time = None
                self.total_paused_duration = timedelta(seconds=0)
                self.seek_time = 0
                await self.clear_task()
                await self.schedule_ui_update()

            except PlaybackPreparationCancelled:
                self.current_song = None
                self.preparation_skipped_song = None
                self.consecutive_play_failures = 0
                self.play_next_song.set()
                continue
            except Exception as e:
                self.handle_after_play(e)
                continue
            finally:
                self.preparing_song = None

            if self.loop_mode == LoopMode.QUEUE and self.current_song:
                self.queue.append(self.current_song)

    def handle_after_play(self, error: Optional[Exception]) -> None:
        if self.is_tts_interrupting: return
        stderr_summary = self.ffmpeg_stderr.summary() if self.ffmpeg_stderr else ""
        self.bot.loop.call_soon_threadsafe(
            lambda: self.bot.loop.create_task(
                self._complete_playback(error, stderr_summary)
            )
        )

    def _remove_song_from_queue(self, song: Song) -> None:
        while True:
            try:
                self.queue.remove(song)
            except ValueError:
                return

    async def _complete_playback(
        self,
        error: Optional[Exception],
        stderr_summary: str = "",
    ) -> None:
        if error is None:
            self.consecutive_play_failures = 0
            self._clear_playback_retry()
            self.playback_retry_cancelled.clear()
            self.ffmpeg_stderr = None
            self.play_next_song.set()
            return

        self.consecutive_play_failures += 1
        failure_count = self.consecutive_play_failures
        song = self.current_song
        if song is not None:
            self.playback_backend.discard(song)
        error_name = type(error).__name__
        details = stderr_summary or str(error)
        details = re.sub(r"https?://\S+", "[URL 생략]", details)[:800]

        if song is not None and failure_count < 3:
            self._remove_song_from_queue(song)
            if self.loop_mode != LoopMode.SONG:
                self.queue.appendleft(song)

            retry_delay = self.PLAYBACK_RETRY_DELAYS[failure_count - 1]
            self.playback_retry_song = song
            self.playback_retry_not_before = time.monotonic() + retry_delay
            self.playback_retry_cancelled.clear()
            self.current_task = (
                f"🔄 음악 스트림 재연결 대기 중... ({retry_delay:.0f}초)"
            )
            await self.schedule_ui_update()

            log_method = logger.error if failure_count == 1 else logger.info
            log_method(
                "[%s] 음악 스트림 재생 실패(%s, %s/3). "
                "%.0f초 후 새 yt-dlp 세션으로 자동 재시도합니다. 상세: %s",
                self.guild.name,
                error_name,
                failure_count,
                retry_delay,
                details,
            )
        else:
            if song is not None:
                self._remove_song_from_queue(song)
            self.current_song = None
            self.consecutive_play_failures = 0
            self._clear_playback_retry()
            self.playback_retry_cancelled.clear()
            logger.error(
                "[%s] 음악 스트림 재생이 3회 실패하여 현재 곡을 건너뜁니다. "
                "마지막 오류(%s): %s",
                self.guild.name,
                error_name,
                details,
            )
            if self.text_channel:
                try:
                    await self.text_channel.send(
                        "🚨 **재생 오류**: YouTube 스트림 연결이 반복적으로 "
                        "거부되어 현재 곡을 건너뜁니다.",
                        delete_after=30,
                    )
                except discord.HTTPException as send_error:
                    logger.warning(
                        "[%s] 재생 오류 안내 전송 실패: %s",
                        self.guild.name,
                        send_error,
                    )

        self.ffmpeg_stderr = None
        self.play_next_song.set()
