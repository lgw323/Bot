"""A bounded subprocess owner with capped pipes and terminate/kill/reap."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from uuid import uuid4

from discordbot.music.domain.failures import safe_failure_fields
from discordbot.platform.errors import CapacityError, DeadlineExceededError, ExternalPermanentError
from discordbot.platform.tasks import TaskSpec, TaskSupervisor


class PremiumOnly(ExternalPermanentError):
    default_safe_message = "⚠️ YouTube Music Premium 전용 음원(또는 멤버십 전용 영상)이라 재생할 수 없습니다."


class UnavailableTrack(ExternalPermanentError):
    default_safe_message = "⚠️ 삭제되었거나 비공개 처리되어 재생할 수 없는 영상입니다."


def child_failure(diagnostic: bytes, returncode: int, name: str) -> ExternalPermanentError:
    """Classify capped stderr in memory; never attach vendor text to an error."""
    reason, error_type = 'child_nonzero', ExternalPermanentError
    if name in {'lookup', 'acquire', 'direct'}:
        text = diagnostic.decode('utf-8', errors='replace').lower()
        if any(term in text for term in ('premium', 'members-only', 'join this channel')):
            reason, error_type = 'provider_rejected', PremiumOnly
        elif any(term in text for term in ('private video', 'video unavailable', 'has been removed')):
            reason, error_type = 'provider_rejected', UnavailableTrack
        else:
            for category, terms in (
                ('auth_required', ('sign in', 'login required', 'not a bot')),
                ('http_forbidden', ('http error 403', '403 forbidden')),
                ('no_audio_format', ('requested format is not available', 'only images')),
                ('js_runtime_missing', ('no supported javascript runtime',)),
                ('timeout', ('timed out',)),
                ('download_failed', ('unable to download', 'download failed')),
            ):
                if any(term in text for term in terms):
                    reason = category
                    break
    return error_type('Music process exited unsuccessfully',
                      context=safe_failure_fields({'reason': reason, 'child_exit_code': returncode}))


class ProcessPool:
    def __init__(self, supervisor: TaskSupervisor, *, active: int = 2, waiting: int = 4,
                 output_bytes: int = 1024 * 1024, kill_seconds: float = 1) -> None:
        if not 1 <= active <= 4 or not 0 <= waiting <= 8 or not 1 <= output_bytes <= 2 * 1024 * 1024 or not 0 < kill_seconds <= 2:
            raise ValueError("invalid subprocess bounds")
        self.supervisor = supervisor
        self.capacity, self.admitted = active + waiting, 0
        self._slots = asyncio.Semaphore(active)
        self.output_bytes, self.kill_seconds = output_bytes, kill_seconds
        self.children: set[asyncio.subprocess.Process] = set()
        self.closed = False

    async def reap(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), self.kill_seconds)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
        # kill is followed by wait, including after a terminate timeout.
        try:
            await asyncio.wait_for(process.wait(), self.kill_seconds)
        except TimeoutError:
            raise DeadlineExceededError("Music child remains owned after kill deadline") from None
        self.children.discard(process)

    async def run(self, arguments: Sequence[str], *, seconds: float, name: str = "provider",
                  consume: Callable[[bytes], Awaitable[None]] | None = None) -> bytes:
        if self.closed or self.admitted >= self.capacity:
            raise CapacityError("Music process capacity exhausted")
        self.admitted += 1
        process = None
        readers: list[asyncio.Task] = []
        try:
            async with asyncio.timeout(seconds):
                async with self._slots:
                    process = await asyncio.create_subprocess_exec(*arguments, stdout=asyncio.subprocess.PIPE,
                                                                   stderr=asyncio.subprocess.PIPE)
                    self.children.add(process)

                    async def drain(stream: asyncio.StreamReader, consumer: Callable | None = None) -> bytes:
                        data = bytearray()
                        while chunk := await stream.read(16384):
                            if consumer:
                                await consumer(chunk)
                                continue
                            data.extend(chunk)
                            if len(data) > self.output_bytes:
                                raise CapacityError("Music process output too large", context={'reason':'output_limit'})
                        return bytes(data)

                    for stream, consumer in ((process.stdout, consume), (process.stderr, None)):
                        identity = uuid4().hex
                        readers.append(self.supervisor.start(TaskSpec("music." + name + ".pipe", "music.process",
                                       identity, identity, seconds + 5), lambda stream=stream, consumer=consumer: drain(stream, consumer)))
                    output, diagnostic = await asyncio.gather(*readers)
                    returncode = await process.wait()
                    if returncode != 0:
                        raise child_failure(diagnostic, returncode, name)
                    return output
        except TimeoutError:
            raise DeadlineExceededError("Music process deadline exceeded", context={'reason':'timeout'}) from None
        except OSError as error:
            reason = ('process_io_failure' if process is not None else
                      'executable_not_found' if isinstance(error, FileNotFoundError) else 'process_start_failure')
            raise ExternalPermanentError("Music process operation failed", context={'reason':reason}) from None
        finally:
            for reader in readers:
                if not reader.done():
                    reader.cancel()
            if process is not None:
                await self.reap(process)
            if readers:
                await asyncio.gather(*readers, return_exceptions=True)
            self.admitted -= 1

    async def close(self) -> None:
        self.closed = True
        for process in tuple(self.children):
            await self.reap(process)
