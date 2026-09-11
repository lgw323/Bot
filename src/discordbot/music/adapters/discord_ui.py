"""Lazy Discord components. Every mutation is routed to the guild actor."""
import asyncio
import hashlib
import re
from dataclasses import replace
from typing import Any
from uuid import uuid4

from discordbot.music.domain.model import LoopMode, Track
from discordbot.music.domain.pages import SongPages
from discordbot.music.ports.repository import Favorite
from discordbot.platform.errors import AppError, AuthorizationError, CapacityError, ConflictError, ExternalPermanentError
from discordbot.storage.ports.contracts import DatabaseRequest


class Responder:
    def __init__(self, interaction: Any) -> None:
        self.interaction = interaction
        self.acknowledged = bool(interaction.response.is_done())
        self.finished = False

    async def _call(self, callback: Any) -> Any:
        try:
            async with asyncio.timeout(3):
                return await callback()
        except BaseException:
            self.finished = True
            raise

    async def defer(self, *, ephemeral: bool = True, thinking: bool = True) -> None:
        if not self.acknowledged and not self.finished:
            self.acknowledged = True
            await self._call(lambda: self.interaction.response.defer(ephemeral=ephemeral, thinking=thinking))

    async def send(self, content: str | None = None, **kwargs: Any) -> Any:
        if self.finished:
            return None
        self.finished = True
        callback = self.interaction.followup.send if self.acknowledged else self.interaction.response.send_message
        self.acknowledged = True
        return await self._call(lambda: callback(content=content, **kwargs))

    async def edit(self, **kwargs: Any) -> Any:
        if self.finished:
            return None
        self.finished = self.acknowledged = True
        return await self._call(lambda: self.interaction.response.edit_message(**kwargs))

    async def modal(self, modal: Any) -> None:
        if self.finished or self.acknowledged:
            raise ConflictError("Music interaction already acknowledged")
        self.finished = self.acknowledged = True
        await self._call(lambda: self.interaction.response.send_modal(modal))


class MusicController:
    def __init__(self, actors: Any, repository: Any, clock: Any, channels: dict[int, int], master: int) -> None:
        self.actors, self.repository, self.clock, self.channels, self.master = actors, repository, clock, channels, master
        self.views: dict[str, tuple[Any, float]] = {}
        self.delete_failures = 0

    def own(self, view: Any, seconds: float = 180) -> Any:
        for key, (old, expires) in tuple(self.views.items()):
            if expires <= self.clock.monotonic() or old.is_finished():
                old.stop()
                del self.views[key]
        if len(self.views) >= 32:
            view.stop()
            raise CapacityError("Music UI capacity exhausted")
        self.views[uuid4().hex] = (view, self.clock.monotonic() + seconds)
        return view

    def close(self) -> None:
        for view, _ in self.views.values(): view.stop()
        self.views.clear()

    async def actor(self, guild_id: int) -> Any:
        if guild_id not in self.channels:
            raise AuthorizationError("Music disabled for this guild")
        return await self.actors(guild_id)

    async def voice(self, actor: Any, member: Any) -> bool:
        channel = getattr(getattr(member, "voice", None), "channel", None)
        state = actor.projection()
        if channel is None:
            if member.id != self.master:
                raise AuthorizationError("requester is not in voice", safe_message="음성 채널에 먼저 참여해주세요.")
            if state.voice_channel_id is None:
                raise AuthorizationError("master has no voice target", safe_message="봇이 현재 음성 채널에 없습니다. 음성 채널에 먼저 참여하거나 봇을 호출해주세요.")
            return False
        if channel.guild.id != actor.guild_id:
            raise AuthorizationError("cross-guild voice target")
        moved = channel.id != state.voice_channel_id
        await actor.ask("connect", channel_id=channel.id)
        return moved

    async def request(self, interaction: Any, query: str, *, modal: bool = False) -> None:
        responder = Responder(interaction)
        try:
            await responder.defer()
            actor = await self.actor(interaction.guild_id)
            channel = self.channels[interaction.guild_id]
            if interaction.channel_id != channel:
                text = f"노래 검색은 <#{channel}> 채널에서만 사용할 수 있습니다." if modal else f"노래 명령어는 <#{channel}> 채널에서만 사용할 수 있습니다."
                await responder.send(text, ephemeral=True)
                return
            await self.voice(actor, interaction.user)
            url = query.strip().startswith(("http://", "https://"))
            future = await actor.ask("lookup", query=query, requester_id=interaction.user.id,
                                     request_id=str(interaction.id), enqueue=url)
            tracks = await future
            if not tracks:
                text = "재생목록을 처리할 수 없거나 비어있습니다." if url and "list=" in query else "노래 정보를 찾을 수 없습니다."
                await responder.send(text, ephemeral=True, delete_after=5)
            elif not url:
                pages = SongPages(interaction.guild_id, interaction.user.id, self.clock.monotonic()+180, tracks)
                await responder.send("**🔎 검색 결과:**", ephemeral=True, view=self.own(build_song_view(self, pages, "search")))
            else:
                text = f"✅ 재생목록에서 **{len(tracks)}**개의 노래를 대기열에 추가했습니다." if "list=" in query else f"✅ 대기열에 **'{tracks[0].title}'** 을(를) 추가했습니다."
                await responder.send(text, ephemeral=True, delete_after=5)
        except asyncio.CancelledError:
            raise
        except AppError as error:
            await responder.send(error.safe_message, ephemeral=True)
        except Exception:
            await responder.send("노래 정보를 가져오는 중 오류가 발생했습니다.", ephemeral=True, delete_after=5)

    async def message(self, message: Any) -> None:
        if message.author.bot or not message.guild or self.channels.get(message.guild.id) != message.channel.id:
            return
        match = re.search(r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/[^\s<>]+", message.content)
        if not match:
            return
        try:
            await message.delete()
        except Exception:
            # Failed deletion must not prevent the original public request.
            self.delete_failures += 1
        try:
            actor = await self.actor(message.guild.id)
            await self.voice(actor, message.author)
            future = await actor.ask("lookup", query=match.group(), requester_id=message.author.id,
                                     request_id=str(message.id), enqueue=True)
            tracks = await future
            text = (f"✅ 재생목록에서 **{len(tracks)}**개의 노래를 대기열에 추가했습니다." if "list=" in match.group()
                    else f"✅ 대기열에 **'{tracks[0].title}'** 을(를) 추가했습니다." if tracks else "노래 정보를 찾을 수 없습니다.")
            await message.channel.send(text, delete_after=5)
        except AppError as error:
            await message.channel.send(error.safe_message, delete_after=8)

    async def favorites(self, guild: int, user: int) -> SongPages:
        tracks = []
        for offset in range(0, 1001, 100):
            values = await self.repository.list_favorites(user, DatabaseRequest.within(3), limit=100, offset=offset)
            if offset == 1000 and values:
                raise CapacityError("favorite view exceeds bounded result capacity")
            tracks.extend(Track(hashlib.sha256(value.url.encode()).hexdigest(), value.url, value.title, 0, user) for value in values)
            if len(values) < 100: break
        return SongPages(guild, user, self.clock.monotonic()+180, tuple(tracks))

    async def action(self, interaction: Any, action: str, state: Any) -> None:
        responder = Responder(interaction)
        try:
            if interaction.guild_id != state.guild_id:
                raise AuthorizationError("cross-guild Music component")
            actor = await self.actor(state.guild_id)
            if action == "search":
                await responder.modal(self.own(build_search_modal(self)))
            elif action == "pause":
                await responder.defer(ephemeral=False, thinking=False)
                await actor.ask("resume" if state.status == "paused" else "pause", session_id=state.session_id)
            elif action == "loop":
                await responder.defer(ephemeral=False, thinking=False)
                await actor.ask("loop")
            elif action == "skip":
                result = await actor.ask("skip", session_id=state.session_id, generation=state.generation)
                await responder.send("⏭️ 현재 노래를 건너뛰었습니다." if result else "건너뛸 노래가 없습니다.", ephemeral=True, **({"delete_after": 5} if result else {}))
            elif action == "leave":
                await responder.defer()
                await actor.ask("leave")
                await responder.send("🚪 음성 채널에서 퇴장했습니다.", ephemeral=True)
            elif action == "autoplay":
                enabled = not actor.projection().autoplay
                await actor.ask("autoplay", enabled=enabled)
                await responder.send(f"🎶 자동 재생을 {'활성화' if enabled else '비활성화'}했습니다.", ephemeral=True, delete_after=5)
            elif action == "favorite":
                current = actor.projection()
                if not current.current or current.session_id != state.session_id:
                    await responder.send("재생 중인 노래가 없습니다.", ephemeral=True)
                    return
                await responder.defer()
                pages = await self.favorites(state.guild_id, interaction.user.id)
                if any(song.url == current.current.url for song in pages.songs):
                    await responder.send("이미 즐겨찾기에 추가된 노래입니다.", ephemeral=True)
                    return
                await self.repository.put_favorite(interaction.user.id, Favorite(current.current.url, current.current.title), DatabaseRequest.within(3))
                await responder.send(f"⭐ '{current.current.title}'을(를) 즐겨찾기에 추가했습니다!", ephemeral=True)
            elif action in {"queue", "favorites"}:
                current = actor.projection()
                pages = (await self.favorites(state.guild_id, interaction.user.id) if action == "favorites" else
                         SongPages(state.guild_id, interaction.user.id, self.clock.monotonic()+180, current.queue, current.revision))
                if not pages.songs and action == "favorites":
                    await responder.send("즐겨찾기 목록이 비어있습니다.", ephemeral=True)
                else:
                    await responder.send("🎶 노래 대기열" if action == "queue" else "💾 보관함", ephemeral=True,
                                         view=self.own(build_song_view(self, pages, action)))
        except AppError as error:
            await responder.send(error.safe_message, ephemeral=True)
        except Exception:
            await responder.send("요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.", ephemeral=True)


def build_search_modal(controller: MusicController) -> Any:
    import discord
    class SearchModal(discord.ui.Modal, title="🎵 노래 검색 및 재생"):
        def __init__(self):
            super().__init__(timeout=180)
            self.query = discord.ui.TextInput(label="검색어 또는 유튜브 URL 입력", placeholder="예: 아이유 밤편지 또는 https://youtu.be/...", required=True, max_length=2048)
            self.add_item(self.query)
        async def on_submit(self, interaction):
            await controller.request(interaction, self.query.value, modal=True)
    return SearchModal()


def build_song_view(controller: MusicController, pages: SongPages, kind: str) -> Any:
    import discord
    class SongView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.songs, self.pages, self.page_index = pages.songs, pages, 0
            self.selected: set[str] = set()
            self.deleting = False
            self.consumed = False
            self.render()

        async def interaction_check(self, interaction):
            try:
                pages.select((), interaction.guild_id, interaction.user.id, controller.clock.monotonic())
                return True
            except AppError as error:
                await Responder(interaction).send(error.safe_message, ephemeral=True)
                return False

        def render(self):
            self.clear_items()
            options = [discord.SelectOption(label=track.title[:100], value=track.item_id,
                       description=f"채널: {track.uploader[:60]} | 길이: {track.duration//60}:{track.duration%60:02d}",
                       default=track.item_id in self.selected) for track in pages.page(self.page_index)]
            if options:
                select = discord.ui.Select(placeholder="재생할 노래를 선택하세요..." if kind == "search" else "노래를 선택하세요...",
                    options=options, max_values=len(options) if kind == "favorites" else 1, custom_id="music:"+kind+":select", row=0)
                async def selected(interaction):
                    if not await self.interaction_check(interaction): return
                    visible = {track.item_id for track in pages.page(self.page_index)}
                    if not set(select.values) <= visible:
                        await Responder(interaction).send("입력값을 확인해 주세요.", ephemeral=True)
                        return
                    self.selected.difference_update(visible)
                    self.selected.update(select.values)
                    if kind == "search": await self.perform(interaction, "add")
                    else:
                        self.render()
                        await Responder(interaction).edit(view=self)
                select.callback = selected
                self.add_item(select)
            if kind == "queue":
                for label, action, custom_id in (("맨 위로", "move", "q_move_top"), ("삭제", "remove", "q_remove"),
                                                  ("섞기", "shuffle", "music:shuffle"), ("전체삭제", "clear", "music:clear")):
                    self.button(label, action, custom_id)
            elif kind == "favorites":
                for label, action in (("전체 선택", "all"), ("선택 해제", "none"), ("삭제" if self.deleting else "대기열에 추가", "add"),
                                      ("추가 모드로 전환" if self.deleting else "삭제 모드로 전환", "mode")):
                    self.button(label, action, "music:favorites:"+action)
            if pages.count > 1:
                self.button("이전", "previous", "music:previous", row=2, disabled=self.page_index == 0)
                self.button("다음", "next", "music:next", row=2, disabled=self.page_index + 1 == pages.count)

        def button(self, label, action, custom_id, row=1, disabled=False):
            button = discord.ui.Button(label=label, custom_id=custom_id, row=row, disabled=disabled)
            async def callback(interaction): await self.perform(interaction, action)
            button.callback = callback
            self.add_item(button)

        async def perform(self, interaction, action):
            responder = Responder(interaction)
            try:
                selected = pages.select(tuple(song.item_id for song in pages.songs if song.item_id in self.selected),
                                        interaction.guild_id, interaction.user.id, controller.clock.monotonic())
                if action in {"previous", "next", "all", "none", "mode"}:
                    if action == "previous": self.page_index = max(0, self.page_index-1)
                    if action == "next": self.page_index = min(pages.count-1, self.page_index+1)
                    if action == "all": self.selected = {song.item_id for song in pages.songs}
                    if action == "none": self.selected.clear()
                    if action == "mode": self.deleting = not self.deleting
                    self.render()
                    await responder.edit(view=self)
                    return
                actor = await controller.actor(pages.guild_id)
                if action == "clear":
                    view = build_clear_confirmation(controller, pages)
                    await responder.send("대기열을 모두 삭제하시겠습니까?", ephemeral=True, view=controller.own(view, 30))
                    return
                await responder.defer()
                if action in {"move", "remove", "shuffle"}:
                    if action != "shuffle" and len(selected) != 1: raise ConflictError("select one queue item")
                    await actor.ask("edit", action=action, item_id=selected[0].item_id if selected else None, revision=pages.revision)
                    await responder.send("🔀 대기열을 섞었습니다!" if action == "shuffle" else "대기열을 수정했습니다.", ephemeral=True, delete_after=5)
                elif action == "add":
                    if not selected: raise ConflictError("no selected Music items")
                    if self.consumed: raise ConflictError("Music selection already consumed")
                    if len(selected) > 50:
                        raise CapacityError("select at most fifty favorites per request")
                    self.consumed = True
                    if kind == "favorites" and self.deleting:
                        count = 0
                        for song in selected:
                            count += await controller.repository.remove_favorite(interaction.user.id, song.url, DatabaseRequest.within(3))
                        await responder.send(f"🗑️ 즐겨찾기에서 {count}개의 노래를 삭제했습니다.", ephemeral=True)
                    else:
                        await controller.voice(actor, interaction.user)
                        if kind == "search":
                            await actor.ask("enqueue", tracks=tuple(replace(song, item_id=uuid4().hex) for song in selected), request_id=str(interaction.id))
                        else:
                            for song in selected:
                                future = await actor.ask("lookup", query=song.url, requester_id=interaction.user.id,
                                                         request_id=str(interaction.id)+song.item_id, enqueue=True)
                                await future
                        await responder.send(f"✅ 대기열에 {len(selected)}개의 노래를 추가했습니다.", ephemeral=True, delete_after=5)
                    self.stop()
            except AppError as error:
                await responder.send(error.safe_message, ephemeral=True)
            except Exception:
                await responder.send("노래 정보를 가져오는 중 오류가 발생했습니다.", ephemeral=True)
    return SongView()


def build_clear_confirmation(controller: MusicController, pages: SongPages) -> Any:
    import discord
    view = discord.ui.View(timeout=30)
    expiry = controller.clock.monotonic()+30
    for label, confirmed in (("확인", True), ("취소", False)):
        button = discord.ui.Button(label=label, custom_id="music:clear:"+str(confirmed))
        async def callback(interaction, confirmed=confirmed):
            responder = Responder(interaction)
            try:
                pages.select((), interaction.guild_id, interaction.user.id, controller.clock.monotonic())
                if controller.clock.monotonic() >= expiry: raise ConflictError("confirmation expired")
                if confirmed:
                    actor = await controller.actor(pages.guild_id)
                    await actor.ask("edit", action="clear", revision=pages.revision)
                await responder.edit(content=f"🗑️ 대기열의 노래 {len(pages.songs)}개를 모두 삭제했습니다." if confirmed else "취소했습니다.", view=None)
                view.stop()
            except AppError as error: await responder.send(error.safe_message, ephemeral=True)
        button.callback = callback
        view.add_item(button)
    return view


def build_dashboard(controller: MusicController, state: Any, top: tuple = ()) -> Any:
    import discord
    view = discord.ui.View(timeout=None)
    controls = (("", "▶️" if state.status == "paused" else "⏸️", "pause", 0), ("", "⏭️", "skip", 0),
                ("", "⏹️", "leave", 0), ("", "⭐", "favorite", 0), ("", "📜", "queue", 0),
                (("반복 없음", "한 곡 반복", "전체 반복")[state.loop.value], ("➡️", "🔂", "🔁")[state.loop.value], "loop", 1),
                ("추천재생: " + ("ON" if state.autoplay else "OFF"), "🤖", "autoplay", 1),
                ("보관함", "💾", "favorites", 1), ("노래 검색", "🔎", "search", 1))
    for label, emoji, action, row in controls:
        button = discord.ui.Button(label=label, emoji=emoji, row=row, custom_id="music:"+action,
                                   disabled=(action in {"pause", "skip", "favorite"} and state.current is None))
        async def callback(interaction, action=action): await controller.action(interaction, action, state)
        button.callback = callback
        view.add_item(button)
    for index, song in enumerate(top[:3]):
        button = discord.ui.Button(label=f"[{('🏆 1위','🥈 2위','🥉 3위')[index]}] {song.title[:40]} ({song.count}회)"[:80],
                                   row=index+2, custom_id="music:top:"+str(index))
        async def callback(interaction, song=song): await controller.request(interaction, song.url)
        button.callback = callback
        view.add_item(button)
    return view


def dashboard_embed(state: Any) -> Any:
    import discord
    title = state.current.title if state.current else "재생 중인 노래가 없습니다."
    embed = discord.Embed(title="🎵 음악 플레이어", description=title[:4096], color=0x5865F2)
    if state.current:
        embed.add_field(name="재생 시간", value=f"{state.elapsed//60}:{state.elapsed%60:02d} / {state.current.duration//60}:{state.current.duration%60:02d}")
    embed.add_field(name=f"대기열 ({len(state.queue)}곡)", value="\n".join(song.title[:100] for song in state.queue[:10]) or "비어있음", inline=False)
    return embed
