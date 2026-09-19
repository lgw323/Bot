"""Explicit Music lifecycle for Discord composition; importing starts nothing."""
import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

from discordbot.music.adapters.audio import DiscordAudio
from discordbot.music.adapters.cache import DiskCache
from discordbot.music.adapters.discord_ui import MusicController, build_dashboard, dashboard_embed
from discordbot.music.adapters.processes import ProcessPool
from discordbot.music.adapters.providers import CachedMediaLibrary, YtDlpProvider
from discordbot.music.adapters.snapshots import SnapshotStore
from discordbot.music.application.actor import MusicActor
from discordbot.music.domain.model import Bounds
from discordbot.platform.errors import CapacityError, ConflictError
from discordbot.platform.tasks import TaskSpec, TaskSupervisor
from discordbot.storage.ports.contracts import DatabaseRequest


class Sleeper:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class MusicResource:
    name = "music"
    required = False

    def __init__(self, bot: Any, repository: Any, clock: Any, executor: Any, *, cache_path: Path,
                 snapshot_path: Path, channels: dict[int, int], master: int, bounds: Bounds = Bounds(),
                 provider: Any = None, library: Any = None, audio_factory: Any = None,
                 direct_until: float | None = None, tts_enabled: bool = True) -> None:
        if len(channels) > bounds.actors:
            raise CapacityError("Music configured guild capacity exceeded")
        self.bot, self.repository, self.clock, self.executor = bot, repository, clock, executor
        self.channels, self.bounds = dict(channels), bounds
        self.supervisor = TaskSupervisor(capacity=96, history_capacity=256, clock=clock)
        self.processes = ProcessPool(self.supervisor)
        self.ffmpeg = ProcessPool(self.supervisor, active=bounds.actors, waiting=0)
        self.cache = DiskCache(cache_path, executor, clock)
        self.snapshots = SnapshotStore(snapshot_path, executor, guilds=bounds.actors)
        self.provider = provider or YtDlpProvider(self.processes)
        self.library = library or CachedMediaLibrary(self.cache, self.processes, direct_until=direct_until)
        self.tts_enabled = tts_enabled
        self.audio_factory = audio_factory or (lambda guild: DiscordAudio(bot, guild, self.ffmpeg))
        self.actors: dict[int, MusicActor] = {}
        self.messages: dict[int, Any] = {}
        self.dashboard_views: dict[int, Any] = {}
        self._cleaned_sessions: dict[int, str | None] = {}
        self._lock = asyncio.Lock()
        self._dirty: dict[int, Any] = {}
        self._refresh_task = self._tick_task = None
        self.controller = MusicController(self.actor, repository, clock, channels, master)
        self.started = self.closed = self.restoring = False
        self.error: str | None = None
        self.failed_restore: set[int] = set()
        self.cog = None

    def _spawn(self, name: str, operation: Any, seconds: float = 60):
        identity = uuid4().hex
        return self.supervisor.start(TaskSpec("music."+name, "music.runtime", identity, identity, seconds), operation)

    async def actor(self, guild: int) -> MusicActor:
        async with self._lock:
            if self.closed or guild not in self.channels or guild in self.failed_restore:
                raise ConflictError("Music guild is unavailable")
            if guild not in self.actors:
                if len(self.actors) >= self.bounds.actors:
                    raise CapacityError("Music actor capacity exhausted")
                volume = await self.repository.get_volume(guild, DatabaseRequest.within(3))
                self.actors[guild] = MusicActor(guild, supervisor=self.supervisor, clock=self.clock,
                    sleeper=Sleeper(), provider=self.provider, library=self.library, audio=self.audio_factory(guild),
                    repository=self.repository, text_channel_id=self.channels[guild], volume=.5 if volume is None else volume,
                    bounds=self.bounds, changed=self.changed)
            return self.actors[guild]

    def changed(self, state: Any) -> None:
        if self.closed or self.restoring or state.guild_id in self.failed_restore:
            return
        self._dirty[state.guild_id] = state
        if self._refresh_task is None:
            self._refresh_task = self._spawn("dashboard-checkpoint", self._refresh)

    async def _refresh(self) -> None:
        try:
            await asyncio.sleep(.25)
            pending, self._dirty = self._dirty, {}
            for guild, state in pending.items():
                try:
                    await self.snapshots.save(state)
                except Exception:
                    self.error = "checkpoint_failed"
                try:
                    await self.dashboard(guild, state)
                except Exception:
                    self.error = "dashboard_failed"
        finally:
            self._refresh_task = None
            if self._dirty and not self.closed:
                self._refresh_task = self._spawn("dashboard-checkpoint", self._refresh)

    async def dashboard(self, guild: int, state: Any) -> None:
        channel = self.bot.get_channel(self.channels[guild])
        if channel is None or channel.guild.id != guild:
            raise ConflictError("Music dashboard channel unavailable")
        top = await self.repository.list_play_counts(guild, DatabaseRequest.within(3), limit=3)
        view = build_dashboard(self.controller, state, top)
        old_view = self.dashboard_views.get(guild)
        try:
            async with asyncio.timeout(5):
                message = self.messages.get(guild)
                if message is None:
                    async for candidate in channel.history(limit=50):
                        if candidate.author.id == self.bot.user.id and candidate.embeds:
                            message = candidate
                            break
                # discord.py indexes callbacks by message/custom_id. Retire
                # the old registration before installing the replacement;
                # stopping it afterwards would remove the new callbacks too.
                if old_view:
                    old_view.stop()
                if message:
                    try:
                        await message.edit(embed=dashboard_embed(state), view=view)
                    except Exception as error:
                        if getattr(error, "status", None) != 404:
                            view.stop()
                            raise
                        message = None
                new_dashboard = message is None
                if message is None:
                    message = await channel.send(embed=dashboard_embed(state), view=view)
                self.messages[guild] = message
                self.dashboard_views[guild] = view
                # Preserve dashboard/pinned messages and bounded jukebox cleanup.
                new_track = state.session_id is not None and self._cleaned_sessions.get(guild) != state.session_id
                if channel.permissions_for(channel.guild.me).manage_messages and (new_dashboard or new_track):
                    await channel.purge(limit=100, check=lambda item: item.id != message.id and not item.pinned
                                        and (new_track or item.author.id == self.bot.user.id))
                self._cleaned_sessions[guild] = state.session_id
        finally:
            if self.dashboard_views.get(guild) is not view:
                view.stop()

    async def ready(self) -> None:
        if self.closed: return
        for guild in self.channels:
            if guild in self.failed_restore: continue
            actor = await self.actor(guild)
            self.changed(actor.projection())

    def _schedule_tick(self) -> None:
        if self.closed or self._tick_task is not None: return
        async def tick():
            try:
                await asyncio.sleep(10)
                await self.cache.cleanup()
                await self.ready()
            finally:
                self._tick_task = None
                if not self.closed: self._schedule_tick()
        self._tick_task = self._spawn("periodic-checkpoint-cache", tick, 30)

    async def start(self) -> None:
        if self.started: return
        if self.closed: raise ConflictError("Music resource closed")
        try:
            await self.cache.start()
            self.restoring = True
            records, failed = await self.snapshots.records()
            self.failed_restore.update(failed)
            for record in records:
                try:
                    actor = await self.actor(record.guild_id)
                    await actor.ask("restore", identity=record.identity, data=record.data,
                                    session_id=record.session_id, revision=record.revision, paused=record.paused)
                    # Retain source until actor ACK. The next checkpoint replaces
                    # the acknowledged source atomically; no crash deletion gap.
                    if record.data.get("voice_channel_id"):
                        await actor.ask("connect", channel_id=record.data["voice_channel_id"])
                    await self.snapshots.save(actor.projection())
                except Exception:
                    self.failed_restore.add(record.guild_id)
                    self.error = "restore_guild_failed"
            self.restoring = False
            self.cog = build_music_cog(self)
            await self.bot.add_cog(self.cog)
            self.started = True
            self._schedule_tick()
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        if self.closed: return
        self.closed = True
        self.controller.close()
        if self.cog:
            try:
                await self.bot.remove_cog(self.cog.qualified_name)
            except Exception:
                self.error = "cog_removal_failed"
        for task in (self._tick_task, self._refresh_task):
            if task: task.cancel()
        await asyncio.gather(*(task for task in (self._tick_task, self._refresh_task) if task), return_exceptions=True)
        for guild, actor in self.actors.items():
            try:
                if guild not in self.failed_restore:
                    await self.snapshots.save(actor.projection())
            except Exception:
                self.error = "shutdown_checkpoint_failed"
            finally:
                try:
                    await actor.close()
                except Exception:
                    self.error = "actor_close_failed"
        for view in self.dashboard_views.values(): view.stop()
        try:
            await self.supervisor.shutdown(grace_seconds=2)
        finally:
            try:
                await self.processes.close()
            finally:
                try:
                    await self.ffmpeg.close()
                finally:
                    await self.cache.close()


def build_music_cog(resource: MusicResource) -> Any:
    import discord
    from discord import app_commands
    from discord.ext import commands
    class MusicCog(commands.Cog):
        @app_commands.command(name="재생", description="유튜브 링크나 검색어로 노래를 재생하고, 봇을 음성 채널로 자동 초대합니다.")
        async def play(self, interaction: discord.Interaction, 검색어: str):
            await resource.controller.request(interaction, 검색어)

        @commands.Cog.listener()
        async def on_ready(self): await resource.ready()

        @commands.Cog.listener()
        async def on_message(self, message): await resource.controller.message(message)

        @commands.Cog.listener()
        async def on_voice_state_update(self, member, before, after):
            guild = member.guild.id
            actor = resource.actors.get(guild)
            if actor is None: return
            if member.id == resource.bot.user.id:
                if before.channel and not after.channel:
                    await actor.ask("disconnected")
                elif after.channel:
                    await actor.ask("connect", channel_id=after.channel.id)
                    if not before.channel:
                        await actor.ask("bot_join", enabled=resource.tts_enabled)
                return
            state = actor.projection()
            if not state.voice_channel_id: return
            channel = resource.bot.get_channel(state.voice_channel_id)
            if after.channel == channel and before.channel != channel:
                name = member.display_name
                name = name[:10]+"..." if len(name)>10 else name
                await actor.ask("tts", text=f"{name}님이 입장하셨습니다.", enabled=resource.tts_enabled)
            if before.channel == channel or after.channel == channel:
                await actor.ask("members", channel_id=channel.id, count=sum(not item.bot for item in channel.members))
    return MusicCog()
