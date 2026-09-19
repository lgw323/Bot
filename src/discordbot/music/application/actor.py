"""One bounded mailbox is the sole writer of a guild's Music state.

Long work only returns immutable results. Cancellation is an optimization; work
identity checks are the correctness boundary. Pumps finish when their mailbox is
empty, so an idle guild never consumes an immortal supervisor task.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from discordbot.music.domain.model import Bounds, LoopMode, Projection, Track, normalize_title, volume_value
from discordbot.music.domain.failures import safe_failure_fields
from discordbot.music.ports.playback import Audio, Media, MediaLibrary, Provider, Sleeper
from discordbot.music.ports.repository import MusicRepository
from discordbot.platform.clock import Clock
from discordbot.platform.errors import AppError, CapacityError, ConflictError, ShutdownError, ValidationError
from discordbot.platform.tasks import TaskSpec, TaskSupervisor
from discordbot.storage.ports.contracts import DatabaseRequest

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Command:
    operation: str
    payload: dict[str, Any]
    response: asyncio.Future[Any]


class MusicActor:
    def __init__(self, guild_id: int, *, supervisor: TaskSupervisor, clock: Clock, sleeper: Sleeper,
                 provider: Provider, library: MediaLibrary, audio: Audio, repository: MusicRepository,
                 text_channel_id: int | None = None, volume: float = .5, bounds: Bounds = Bounds(),
                 changed: Callable[[Projection], None] | None = None,
                 fail_fast: bool | Callable[[], bool] = False) -> None:
        self.guild_id, self.bounds = guild_id, bounds
        self.supervisor, self.clock, self.sleeper = supervisor, clock, sleeper
        self.provider, self.library, self.audio, self.repository = provider, library, audio, repository
        self._mailbox: deque[Command] = deque()
        self._pump_task: asyncio.Task | None = None
        self._jobs: dict[str, tuple[str, asyncio.Task]] = {}
        self._retired: set[asyncio.Task] = set()
        self._queue: list[Track] = []
        self._current: Track | None = None
        self._session: str | None = None
        self._attempt: str | None = None
        self._media: Media | None = None
        self._status = "idle"
        self._generation = self._revision = self._failures = 0
        self._volume, self._loop, self._autoplay = volume_value(volume), LoopMode.NONE, False
        self._text_channel, self._voice_channel = text_channel_id, None
        self._connected, self._closed, self._accepting = False, False, True
        self._offset, self._started_at = 0, None
        self._retry_at: float | None = None
        self._error: str | None = None
        self._history: deque[str] = deque(maxlen=20)
        self._history_urls: deque[str] = deque(maxlen=20)
        self._requests: deque[tuple[str, str, int, bool, asyncio.Future]] = deque()
        self._receipts: deque[str] = deque(maxlen=128)
        self._tts: deque[str] = deque()
        self._resume_paused = False
        self._restore_identity: str | None = None
        self.changed = changed
        self.fail_fast, self.smoke_failed = fail_fast, False

    def _spec(self, name: str, identity: str, seconds: float) -> TaskSpec:
        return TaskSpec(name="music." + name, owner="music.actor", work_id=identity,
                        correlation_id=identity, deadline_seconds=seconds)

    def post(self, operation: str, **payload: Any) -> asyncio.Future:
        if self._closed or (not self._accepting and operation != "close"):
            raise ShutdownError("Music actor is closed")
        internal = operation in {"started", "ended", "result", "close"}
        if len(self._mailbox) >= self.bounds.mailbox + (16 if internal else 0):
            raise CapacityError("Music mailbox is full")
        future = asyncio.get_running_loop().create_future()
        command = Command(operation, payload, future)
        self._mailbox.append(command)
        try:
            if self._pump_task is None:
                self._pump_task = self.supervisor.start(self._spec("mailbox", uuid4().hex, 120), self._pump)
        except BaseException:
            self._mailbox.pop()
            raise
        # Callback-originated results have no waiter. Observe errors without hiding
        # them from an explicit awaiter, and never log payloads/URLs/user IDs.
        future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        return future

    async def ask(self, operation: str, **payload: Any) -> Any:
        return await asyncio.shield(self.post(operation, **payload))

    def projection(self) -> Projection:
        elapsed = self._offset
        if self._started_at is not None:
            elapsed += max(0, self.clock.monotonic() - self._started_at)
        return Projection(self.guild_id, self._revision, self._generation, tuple(self._queue), self._current,
                          self._session, self._attempt, self._status,
                          int(min(elapsed, self._current.duration)) if self._current else 0,
                          self._volume, self._loop, self._autoplay, self._text_channel, self._voice_channel,
                          self._retry_at, self._error, self._status == "paused" or self._resume_paused)

    async def _pump(self) -> None:
        try:
            while self._mailbox:
                command = self._mailbox.popleft()
                try:
                    result = await self._dispatch(command.operation, command.payload)
                    if command.operation != "inspect" and result is not False:
                        self._revision += 1
                    if self.changed and command.operation != "inspect" and result is not False:
                        try:
                            self.changed(self.projection())
                        except Exception:
                            self._error = "dashboard_unavailable"
                    if not command.response.done():
                        command.response.set_result(result)
                except asyncio.CancelledError:
                    if not command.response.done():
                        command.response.set_exception(ShutdownError("Music command interrupted"))
                    raise
                except Exception as error:
                    logger.warning('music.command_failed', extra={'fields':{
                        'stage':command.operation if command.operation in {'connect','enqueue','lookup','started','ended','result','tts','leave','close'} else 'control',
                        'error_code':error.code.value if isinstance(error, AppError) else 'internal'}})
                    if not command.response.done():
                        command.response.set_exception(error)
        finally:
            self._pump_task = None
            while self._mailbox:
                pending = self._mailbox.popleft()
                if not pending.response.done():
                    pending.response.set_exception(ShutdownError("Music pump stopped"))

    def _cancel(self, name: str) -> None:
        job = self._jobs.pop(name, None)
        if job:
            job[1].cancel()
            self._retired.add(job[1])
            job[1].add_done_callback(self._retired.discard)

    def _work(self, name: str, operation: Callable[[], Awaitable[Any]], seconds: float) -> None:
        self._cancel(name)
        token = uuid4().hex

        async def run() -> None:
            value, error = None, None
            fields = {'stage':name, 'work_id':token}
            logger.info('music.work_started', extra={'fields':fields})
            try:
                async with asyncio.timeout(seconds):
                    value = await operation()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = type(exc).__name__
                logger.warning('music.work_failed', extra={'fields':dict(fields,
                    error_code=exc.code.value if isinstance(exc, AppError) else 'internal',
                    **safe_failure_fields(exc.context if isinstance(exc, AppError) else {}))})
            else:
                logger.info('music.work_succeeded', extra={'fields':fields})
            try:
                future = self.post("result", name=name, token=token, value=value, error=error)
                try:
                    accepted = await asyncio.shield(future)
                except asyncio.CancelledError:
                    # The result may already have transferred its cache lease.
                    # Resolve that transfer before deciding who releases it.
                    accepted = await asyncio.shield(future)
            except (ShutdownError, CapacityError):
                accepted = False
            if isinstance(value, Media) and not accepted:
                await self.library.release(value)

        self._jobs[name] = (token, self.supervisor.start(self._spec(name, token, seconds + 10), run))

    async def _stop_audio(self, *, corrupt: bool = False) -> None:
        self._offset = self.projection().elapsed
        self._started_at, self._attempt = None, None
        self._cancel("prepare")
        self._cancel("start")
        self._cancel("retry")
        self._retry_at = None
        try:
            await self.audio.stop()
        finally:
            if self._media:
                media, self._media = self._media, None
                await self.library.release(media, corrupt=corrupt)

    def _prepare(self) -> None:
        if not self._current or not self._connected or self._announcement_pending():
            return
        track = self._current
        self._status = "preparing"
        try:
            self._work("prepare", lambda: self.library.acquire(track), self.bounds.acquire_seconds)
        except CapacityError:
            self._status = "idle"
            self._error = "preparation_capacity_exhausted"

    def _advance(self, previous: Track | None = None) -> None:
        self._current, self._session, self._attempt = None, None, None
        self._offset, self._started_at, self._failures = 0, None, 0
        self._status = "idle"
        if self._queue:
            self._current = self._queue.pop(0)
            self._session = uuid4().hex
            self._prepare()
        elif self._autoplay and previous and self._connected:
            self._history.append(normalize_title(previous.title))
            self._history_urls.append(previous.url)
            query = "ytsearch10:" + previous.uploader
            featured = re.search(r"(?i)(?:feat|ft|with)\.?\s+([^()\[\]\-]+)", previous.title)
            if featured and random.random() < .3:
                query = "ytsearch10:" + featured.group(1).strip()
            self._work("autoplay", lambda: self.provider.lookup(query, previous.requester_id, limit=10), self.bounds.provider_seconds)

    async def _failed(self) -> None:
        if self._smoke_enabled():
            await self._stop_for_smoke()
            return
        await self._stop_audio(corrupt=True)
        self._failures += 1
        if self._failures >= 3:
            self._error = "playback_failed_three_times"
            self._advance()
        else:
            delay = (3, 8)[self._failures - 1]
            self._retry_at = self.clock.monotonic() + delay
            self._status = "retry"
            self._work("retry", lambda: self.sleeper.sleep(delay), delay + 5)

    def _smoke_enabled(self) -> bool:
        return self.fail_fast() if callable(self.fail_fast) else self.fail_fast

    async def _stop_for_smoke(self) -> None:
        """Latch admission before yielding; retain the newest queue for preservation."""
        self.smoke_failed = True
        self._accepting = False
        self._status, self._error = 'failed', 'live_smoke_failed'
        logger.warning('music.smoke_failed', extra={'fields':{'stage':'live_smoke', 'result':'failed'}})
        for name in tuple(self._jobs): self._cancel(name)
        while self._requests:
            future = self._requests.popleft()[-1]
            if not future.done(): future.set_exception(ShutdownError('Music smoke stopped after first failure'))
        await self._stop_audio(corrupt=True)

    def _notify(self, attempt: str, failed: bool) -> None:
        if attempt != self._attempt or any(c.operation == "ended" and c.payload.get("attempt") == attempt for c in self._mailbox):
            return
        try:
            logger.info('music.playback_ended', extra={'fields':{'stage':'playback_callback',
                'work_id':attempt, 'result':'failed' if failed else 'completed'}})
            self.post("ended", attempt=attempt, failed=failed)
        except (ShutdownError, CapacityError):
            # Internal events have 16 reserved slots; repeated callbacks for an
            # attempt coalesce above. A closed actor intentionally ignores them.
            return

    def _start(self, media: Media, *, tts: bool = False) -> None:
        self._media, self._attempt = media, uuid4().hex
        attempt, session, track = self._attempt, self._session, self._current
        offset, volume = (0, 2.) if tts else (self._offset, self._volume)
        self._status = "tts_starting" if tts else "starting"

        async def start() -> None:
            await self.audio.start(media, attempt, offset, volume, self._notify)
            # Queue the durable start fact before any further cancellable await.
            # Accounting remains valid even if skip invalidates this attempt.
            future = self.post("started", attempt=attempt, session=session, track=track, tts=tts)
            await asyncio.shield(future)

        self._work("start", start, 10)

    def _next_request(self) -> None:
        if not self._requests or "lookup" in self._jobs:
            return
        _, query, requester, _, _ = self._requests[0]
        limit = 50 if "list=" in query else 3
        target = query if query.startswith(("http://", "https://", "ytsearch")) else "ytsearch3:" + query
        try:
            self._work("lookup", lambda: self.provider.lookup(target, requester, limit=limit), self.bounds.provider_seconds)
        except CapacityError:
            while self._requests:
                future = self._requests.popleft()[-1]
                if not future.done():
                    future.set_exception(CapacityError("Music provider admission exhausted"))

    def _enqueue(self, tracks: tuple[Track, ...]) -> None:
        if len(self._queue) + len(tracks) > self.bounds.queue:
            raise CapacityError("Music queue is full")
        ids = {t.item_id for t in self._queue}
        if self._current:
            ids.add(self._current.item_id)
        if len({t.item_id for t in tracks}) != len(tracks) or any(t.item_id in ids for t in tracks):
            raise ConflictError("duplicate queue item identity")
        self._cancel("autoplay")
        self._queue.extend(tracks)
        if self._announcement_pending():
            return
        if self._current is None:
            self._advance()
        elif self._status == "idle":
            self._prepare()

    async def _dispatch(self, op: str, p: dict[str, Any]) -> Any:
        if self.smoke_failed and op not in {'close', 'inspect'}:
            if op == 'result': return False
            raise ShutdownError('Music smoke stopped after first failure')
        if op == "inspect":
            return self.projection()
        if op == "enqueue":
            receipt = p.get("request_id")
            if receipt and receipt in self._receipts:
                return False
            self._enqueue(tuple(p["tracks"]))
            logger.info('music.enqueued', extra={'fields':{'stage':'enqueue', 'count':len(p['tracks'])}})
            if receipt:
                self._receipts.append(receipt)
            return True
        if op == "lookup":
            if len(self._requests) >= self.bounds.requests:
                raise CapacityError("Music requests are full")
            receipt = p["request_id"]
            if receipt in self._receipts or any(r[0] == receipt for r in self._requests):
                raise ConflictError("duplicate Music request")
            query = p["query"].strip()
            if not query or len(query) > 2048:
                raise ValidationError("invalid music query")
            future = asyncio.get_running_loop().create_future()
            future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
            self._requests.append((receipt, query, p["requester_id"], p.get("enqueue", True), future))
            self._next_request()
            return future
        if op == "connect":
            channel = p["channel_id"]
            if not isinstance(channel, int) or channel < 1:
                raise ValidationError("invalid voice channel")
            async with asyncio.timeout(20):
                await self.audio.connect(channel)
            logger.info('music.voice_connected', extra={'fields':{'stage':'voice_connection'}})
            self._voice_channel, self._connected = channel, True
            self._cancel("reconnect")
            self._cancel("empty")
            if self._current and self._status in {"idle", "disconnected"}:
                self._prepare()
            elif self._current is None and self._queue and not self._announcement_pending():
                self._advance()
        elif op == "started":
            if not p["tts"] and p["track"] is not None:
                await self.repository.record_start(self.guild_id, p["session"], p["track"].url,
                                                   p["track"].title, DatabaseRequest.within(3))
            if p["attempt"] == self._attempt:
                self._status = "tts" if p["tts"] else "playing"
                self._started_at = None if p["tts"] else self.clock.monotonic()
                if not p["tts"] and self._resume_paused:
                    await self.audio.pause()
                    self._status, self._started_at, self._resume_paused = "paused", None, False
        elif op == "ended":
            if p["attempt"] != self._attempt:
                return False
            if self._smoke_enabled() and p['failed']:
                await self._stop_for_smoke()
                return True
            tts = self._status.startswith("tts")
            previous = self._current
            await self._stop_audio(corrupt=p["failed"])
            if tts:
                self._status = "idle"
                self._continue_after_announcement()
            elif p["failed"]:
                await self._failed()
            else:
                if previous and self._loop == LoopMode.SONG:
                    self._queue.insert(0, previous)
                elif previous and self._loop == LoopMode.QUEUE:
                    self._queue.append(previous)
                self._advance(previous)
        elif op == "skip":
            if p.get("session_id") != self._session or p.get("generation", self._generation) != self._generation or self._current is None:
                return False
            self._generation += 1
            previous = self._current
            keep_in_loop = self._loop == LoopMode.QUEUE and self._status in {"playing", "paused"}
            self._cancel("autoplay")
            self._cancel("tts")
            self._tts.clear()
            await self._stop_audio()
            self._resume_paused = False
            if keep_in_loop:
                self._queue.append(previous)
            self._advance()
            return True
        elif op in {"pause", "resume"}:
            if p.get("session_id") != self._session:
                raise ConflictError("stale playback control")
            if op == "pause" and self._status == "playing":
                self._offset = self.projection().elapsed
                await self.audio.pause()
                self._status, self._started_at = "paused", None
            elif op == "resume" and self._status == "paused":
                await self.audio.resume()
                self._status, self._started_at = "playing", self.clock.monotonic()
        elif op == "loop":
            self._loop = LoopMode((self._loop.value + 1) % 3)
        elif op == "autoplay":
            self._autoplay = bool(p["enabled"])
            if not self._autoplay:
                self._cancel("autoplay")
        elif op == "volume":
            value = volume_value(p["value"])
            await self.repository.set_volume(self.guild_id, value, DatabaseRequest.within(3))
            self._volume = value
        elif op == "edit":
            action = p["action"]
            if action in {"clear", "shuffle"}:
                if p["revision"] != self._revision:
                    raise ConflictError("stale queue confirmation")
                if action == "clear":
                    self._queue.clear()
                else:
                    random.shuffle(self._queue)
            else:
                item = next((t for t in self._queue if t.item_id == p["item_id"]), None)
                if item is None:
                    raise ConflictError("queue item no longer exists")
                if action not in {"remove", "move"}:
                    raise ValidationError("invalid queue action")
                self._queue.remove(item)
                if action == "move":
                    self._queue.insert(0, item)
            self._cancel("autoplay")
        elif op == "disconnected":
            self._resume_paused = self._status == "paused"
            await self._stop_audio()
            self._connected, self._status = False, "disconnected"
            self._generation += 1
            self._cancel("tts")
            self._cancel("autoplay")
            self._tts.clear()
            if self._current or self._queue:
                self._work("reconnect", lambda: self.sleeper.sleep(8), 13)
            else:
                await self._leave()
        elif op == "members":
            if p["channel_id"] == self._voice_channel:
                self._cancel("empty")
                if p["count"] == 0:
                    self._work("empty", lambda: self.sleeper.sleep(2), 7)
        elif op == "bot_join":
            if p.get("enabled", True):
                self._work("join-tts", lambda: self.sleeper.sleep(1.5), 7)
        elif op == "tts":
            if not p.get("enabled", True) or not self._connected:
                return False
            if len(self._tts) >= self.bounds.tts_queue:
                raise CapacityError("TTS queue full")
            text = p["text"]
            if not isinstance(text, str) or not 0 < len(text) <= 200:
                raise ValidationError("invalid TTS input")
            self._tts.append(text)
            self._start_tts_generation()
        elif op == "restore":
            identity = p["identity"]
            if self._restore_identity == identity:
                return False
            if self._current or self._queue or self._restore_identity:
                raise ConflictError("stale restore")
            data = p["data"]
            tracks = tuple(Track.from_legacy(d) for d in data.get("queue", ()))
            current = Track.from_legacy(data["current_song"]) if data.get("current_song") else None
            if len(tracks) > self.bounds.queue:
                raise CapacityError("snapshot queue too large")
            volume = volume_value(data.get("volume", self._volume))
            try:
                loop = LoopMode[data.get("loop_mode", "NONE")]
                offset = int(data.get("elapsed_seconds", 0))
                if not 0 <= offset <= 86400 or not isinstance(data.get("auto_play_enabled", False), bool):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise ValidationError("invalid snapshot settings") from None
            self._queue, self._current = list(tracks), current
            self._volume, self._loop, self._offset = volume, loop, offset
            self._autoplay = data.get("auto_play_enabled", False)
            self._text_channel = data.get("text_channel_id")
            self._voice_channel = data.get("voice_channel_id")
            self._session = p.get("session_id") or (identity + ":" + str(self.guild_id) if current else None)
            self._restore_identity = identity
            self._revision = max(self._revision, p.get("revision", 0))
            self._resume_paused = p.get("paused", False)
            return True
        elif op == "leave":
            await self._leave()
        elif op == "close":
            await self._leave()
            self._closed = True
        elif op == "result":
            job = self._jobs.get(p["name"])
            if job is None or job[0] != p["token"]:
                return False
            del self._jobs[p["name"]]
            return await self._result(p["name"], p["value"], p["error"])
        else:
            raise ValidationError("unknown Music command")
        return True

    def _start_tts_generation(self) -> None:
        if self._tts and "tts" not in self._jobs and not self._status.startswith("tts"):
            text = self._tts.popleft()
            self._work("tts", lambda: self.library.speech(text), 20)

    def _announcement_pending(self) -> bool:
        return self._status.startswith("tts") or "tts" in self._jobs

    def _continue_after_announcement(self) -> None:
        self._start_tts_generation()
        if self._announcement_pending() or self._status != "idle":
            return
        if self._current:
            self._prepare()
        elif self._queue:
            self._advance()

    async def _result(self, name: str, value: Any, error: str | None) -> bool:
        if error and self._smoke_enabled() and name in {'lookup', 'prepare', 'start', 'tts'}:
            await self._stop_for_smoke()
            return True
        if name == "lookup":
            receipt, _, _, enqueue, future = self._requests.popleft()
            if future.cancelled():
                self._next_request()
                return True
            try:
                if error:
                    safe = {"PremiumOnly": "⚠️ YouTube Music Premium 전용 음원(또는 멤버십 전용 영상)이라 재생할 수 없습니다.",
                            "UnavailableTrack": "⚠️ 삭제되었거나 비공개 처리되어 재생할 수 없는 영상입니다."}.get(error,
                            "노래 정보를 가져오는 중 오류가 발생했습니다.")
                    raise ValidationError("music provider failed", safe_message=safe)
                tracks = tuple(value[:50])
                if enqueue:
                    self._enqueue(tracks)
                self._receipts.append(receipt)
                if not future.done():
                    future.set_result(tracks)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            self._next_request()
        elif error:
            self._error = "music_" + name + "_failed"
            if name in {"prepare", "start"}:
                if self._status.startswith("tts"):
                    await self._stop_audio()
                    self._status = "idle"
                    self._continue_after_announcement()
                else:
                    await self._failed()
            elif name == "tts":
                self._continue_after_announcement()
        elif name == "prepare":
            self._start(value)
        elif name == "retry":
            self._retry_at = None
            self._prepare()
        elif name == "autoplay":
            candidates = []
            for candidate in value:
                normalized = normalize_title(candidate.title)
                words = set(normalized.split())
                previous = self._history[-1] if self._history else ""
                old_words = set(previous.split())
                similar = (previous in normalized or normalized in previous or
                           (words and old_words and len(words & old_words) / max(len(words), len(old_words)) > .5))
                if (90 < candidate.duration < 600 and normalized not in self._history and not similar
                        and candidate.url not in self._history_urls):
                    candidates.append(candidate)
            if candidates:
                self._enqueue((random.choice(candidates),))
        elif name == "join-tts":
            await self._dispatch("tts", {"text": "노래봇이 입장했습니다."})
        elif name in {"empty", "reconnect"}:
            await self._leave()
        elif name == "tts":
            self._resume_paused = self._status == "paused"
            await self._stop_audio()
            self._start(value, tts=True)
        return True

    async def _leave(self) -> None:
        self._generation += 1
        for name in tuple(self._jobs):
            self._cancel(name)
        while self._requests:
            future = self._requests.popleft()[-1]
            if not future.done():
                future.set_exception(ShutdownError("Music request cancelled"))
        try:
            await self._stop_audio()
        finally:
            self._queue.clear()
            self._tts.clear()
            self._current, self._session, self._voice_channel = None, None, None
            self._connected, self._status, self._offset = False, "idle", 0
            self._resume_paused = False
            await self.audio.disconnect()

    async def close(self) -> None:
        if self._closed:
            return
        future = self.post("close")
        self._accepting = False
        try:
            await asyncio.shield(future)
        finally:
            self._closed = True
            if self._retired:
                await asyncio.gather(*tuple(self._retired), return_exceptions=True)
