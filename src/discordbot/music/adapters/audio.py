"""Discord consumes bounded PCM frames; this adapter owns the FFmpeg child."""
import asyncio
import logging
import queue
from typing import Any
from uuid import uuid4

from discordbot.music.adapters.processes import ProcessPool
from discordbot.music.ports.playback import Media
from discordbot.platform.errors import AuthorizationError, CapacityError, ExternalPermanentError
from discordbot.platform.tasks import TaskSpec

logger = logging.getLogger(__name__)


class DiscordAudio:
    def __init__(self, bot: Any, guild_id: int, pool: ProcessPool, *, executable: str = "ffmpeg") -> None:
        self.bot, self.guild_id, self.pool, self.executable = bot, guild_id, pool, executable
        self.voice = None
        self._decoder = None
        self._source = None
        self._process = None
        self._admitted = False
        self._control_lock = asyncio.Lock()

    async def connect(self, channel_id: int) -> None:
        channel = self.bot.get_channel(channel_id)
        if channel is None or channel.guild.id != self.guild_id:
            raise AuthorizationError("invalid Music voice channel")
        if self.voice and self.voice.is_connected():
            if self.voice.channel.id != channel_id:
                await self.voice.move_to(channel)
        else:
            self.voice = await channel.connect(timeout=20., self_deaf=True)

    async def start(self, media: Media, attempt: str, seek: int, volume: float, notify: Any) -> None:
        async with self._control_lock:
            await self._start(media, attempt, seek, volume, notify)

    async def _start(self, media: Media, attempt: str, seek: int, volume: float, notify: Any) -> None:
        import discord
        if self.voice is None or not self.voice.is_connected():
            raise ExternalPermanentError("Music voice is disconnected")
        await self._stop()
        if self.pool.closed or self.pool.admitted >= self.pool.capacity:
            raise CapacityError("FFmpeg capacity exhausted")
        self.pool.admitted += 1
        self._admitted = True
        frames: queue.Queue[bytes] = queue.Queue(maxsize=100)
        first_frame = asyncio.Event()
        finished = False
        failure = False
        loop = asyncio.get_running_loop()

        class Source(discord.AudioSource):
            def read(self):
                # discord.py owns its existing AudioPlayer thread. No new thread
                # or executor is created by this source.
                while not finished:
                    try: return frames.get(timeout=.1)
                    except queue.Empty: continue
                try: return frames.get_nowait()
                except queue.Empty: return b""
            def is_opus(self): return False
            def cleanup(self):
                nonlocal finished
                finished = True

        async def decode(process):
            nonlocal finished, failure
            stderr_task = None
            try:
                async def stderr():
                    count = 0
                    while chunk := await process.stderr.read(4096):
                        count += len(chunk)
                        if count > 65536: raise CapacityError("FFmpeg stderr limit")
                identity = uuid4().hex
                stderr_task = self.pool.supervisor.start(TaskSpec("music.ffmpeg.stderr", "music.audio", identity, identity, 86400), stderr)
                while True:
                    try: frame = await asyncio.wait_for(process.stdout.readexactly(3840), 30)
                    except asyncio.IncompleteReadError as end:
                        frame = end.partial
                        if frame:
                            frame += b"\0" * (3840-len(frame))
                        else: break
                    while frames.full():
                        if stderr_task.done(): await stderr_task
                        await asyncio.sleep(.02)
                    frames.put_nowait(frame)
                    first_frame.set()
                if await process.wait() != 0:
                    raise ExternalPermanentError("FFmpeg decode failed")
                await stderr_task
            except asyncio.CancelledError:
                raise
            except Exception:
                failure = True
                logger.warning('music.decoder_failed', extra={'fields':{'stage':'pcm_decode', 'work_id':attempt}})
            finally:
                finished = True
                first_frame.set()
                if stderr_task:
                    stderr_task.cancel()
                    await asyncio.gather(stderr_task, return_exceptions=True)
                await self.pool.reap(process)
                if self._admitted:
                    self._admitted = False
                    self.pool.admitted -= 1

        try:
            network_options = ("-rw_timeout", "10000000", "-reconnect", "1", "-reconnect_delay_max", "3") if media.key.startswith("direct:") else ()
            self._process = await asyncio.create_subprocess_exec(self.executable, "-nostdin", "-loglevel", "error", *network_options,
                "-ss", str(seek), "-i", media.path, "-vn", "-f", "s16le", "-ar", "48000", "-ac", "2", "pipe:1",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            self.pool.children.add(self._process)
            logger.info('music.ffmpeg_started', extra={'fields':{'stage':'ffmpeg_start', 'work_id':attempt}})
            identity = uuid4().hex
            self._decoder = self.pool.supervisor.start(TaskSpec("music.ffmpeg.decode", "music.audio", identity, identity, 86400),
                                                        lambda process=self._process: decode(process))
            await asyncio.wait_for(first_frame.wait(), 5)
            if failure or frames.empty():
                raise ExternalPermanentError("FFmpeg produced no playable audio")
            logger.info('music.first_pcm', extra={'fields':{'stage':'first_pcm', 'work_id':attempt}})
            self._source = discord.PCMVolumeTransformer(Source(), volume=volume)
            self.voice.play(self._source, after=lambda error: loop.call_soon_threadsafe(notify, attempt, bool(error) or failure))
            logger.info('music.playback_accepted', extra={'fields':{'stage':'voice_playback_acceptance', 'work_id':attempt}})
        except BaseException:
            if self._decoder:
                await self._stop()
            else:
                if self._process:
                    await self.pool.reap(self._process)
                if self._admitted:
                    self._admitted = False
                    self.pool.admitted -= 1
            raise

    async def stop(self) -> None:
        async with self._control_lock:
            await self._stop()

    async def _stop(self) -> None:
        failure = False
        if self.voice:
            try:
                self.voice.stop()
            except Exception:
                failure = True
        decoder, self._decoder = self._decoder, None
        if decoder:
            decoder.cancel()
            await asyncio.gather(decoder, return_exceptions=True)
        if self._process:
            await self.pool.reap(self._process)
        if self._admitted:
            self._admitted = False
            self.pool.admitted -= 1
        if self._source:
            self._source.cleanup()
            self._source = None
        self._process = None
        if failure:
            raise ExternalPermanentError("Music voice stop failed after decoder cleanup")

    async def pause(self) -> None:
        if self.voice: self.voice.pause()

    async def resume(self) -> None:
        if self.voice: self.voice.resume()

    async def disconnect(self) -> None:
        async with self._control_lock:
            try:
                await self._stop()
            finally:
                if self.voice:
                    voice, self.voice = self.voice, None
                    async with asyncio.timeout(3):
                        await voice.disconnect(force=True)
