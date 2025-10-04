from typing import List
import discord
from discord import ui

# --- 이 파일은 UI 관련 클래스만 모아놓은 곳입니다. ---

class VolumeModal(ui.Modal, title="🔊 볼륨 조절"):
    volume_input = ui.TextInput(label="볼륨 (0 ~ 100)", placeholder="예: 75", required=True, min_length=1, max_length=3)
    def __init__(self, cog, state):
        super().__init__()
        self.cog, self.state = cog, state
    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_volume = int(self.volume_input.value)
            if not (0 <= new_volume <= 100): raise ValueError
            await self.cog.handle_volume(interaction, new_volume / 100.0)
        except ValueError:
            await interaction.response.send_message("0에서 100 사이의 숫자만 입력해주세요.", ephemeral=True)

class SearchSelect(ui.Select):
    def __init__(self, cog, search_results: List[dict]):
        self.cog = cog
        self.search_results = search_results
        options = []
        for i, result in enumerate(search_results):
            duration = result.get('duration', 0)
            minutes, seconds = divmod(duration, 60)
            duration_str = f"{minutes}:{seconds:02d}"
            uploader = result.get('uploader', 'N/A')
            
            options.append(
                discord.SelectOption(
                    label=f"{result.get('title', '알 수 없는 제목')[:95]}",
                    value=str(i),
                    description=f"채널: {uploader[:30]} | 길이: {duration_str}"
                )
            )
        super().__init__(placeholder="재생할 노래를 선택하세요...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_index = int(self.values[0])
        selected_song_data = self.search_results[selected_index]
        await self.cog.queue_song(interaction, selected_song_data)
        self.view.stop()
        await interaction.edit_original_response(content="✅ 선택한 노래를 대기열에 추가했습니다.", view=None)

class QueueSelect(ui.Select):
    def __init__(self, songs): 
        options = [discord.SelectOption(label=f"{i+1}. {song.title[:95]}", value=str(i)) for i, song in enumerate(songs)]
        super().__init__(placeholder="관리할 노래를 선택하세요...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        self.view.selected_index = int(self.values[0])
        for item in self.view.children:
            if isinstance(item, ui.Button) and item.custom_id in ["q_move_top", "q_remove"]:
                 item.disabled = False
        await self.view.update_view(interaction, "노래를 선택했습니다. 아래 버튼으로 관리하세요.", bold_selection=True)

class ConfirmClearView(ui.View):
    def __init__(self, cog, interaction: discord.Interaction, queue_view):
        super().__init__(timeout=30)
        self.cog = cog
        self.original_interaction = interaction
        self.queue_view = queue_view
        self.message = None

    @ui.button(label="확인", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.cog.handle_clear_queue(interaction, self.original_interaction)
        self.stop()

    @ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.original_interaction.edit_original_response(content="취소되었습니다.", view=self.queue_view)
        self.stop()

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content="시간이 초과되어 취소되었습니다.", view=None)
            except discord.HTTPException:
                pass

class QueueManagementView(ui.View):
    def __init__(self, cog, state):
        super().__init__(timeout=180)
        self.cog, self.state, self.selected_index = cog, state, None
        self.songs = list(self.state.queue)[:25]
        self.build_view()
    
    def build_view(self):
        self.clear_items()
        
        if self.songs:
            self.add_item(QueueSelect(self.songs))

        is_selection_made = self.selected_index is not None
        
        move_top_button = ui.Button(label="맨 위로", style=discord.ButtonStyle.green, disabled=not is_selection_made, custom_id="q_move_top", row=1)
        move_top_button.callback = self.move_to_top
        self.add_item(move_top_button)

        remove_button = ui.Button(label="삭제", style=discord.ButtonStyle.red, disabled=not is_selection_made, custom_id="q_remove", row=1)
        remove_button.callback = self.remove_song
        self.add_item(remove_button)

        is_queue_empty = not self.state.queue
        shuffle_button = ui.Button(label="섞기", style=discord.ButtonStyle.blurple, emoji="🔀", row=2, disabled=len(self.state.queue) < 2)
        shuffle_button.callback = self.shuffle
        self.add_item(shuffle_button)
        
        clear_button = ui.Button(label="전체삭제", style=discord.ButtonStyle.danger, emoji="🗑️", row=2, disabled=is_queue_empty)
        clear_button.callback = self.clear_queue
        self.add_item(clear_button)

    async def move_to_top(self, interaction: discord.Interaction):
        if self.selected_index is not None and self.selected_index < len(list(self.state.queue)):
            song_to_move = list(self.state.queue)[self.selected_index]
            self.state.queue.remove(song_to_move)
            self.state.queue.insert(0, song_to_move)
            await self.update_view(interaction, f"✅ '{song_to_move.title}'을(를) 대기열 맨 위로 옮겼습니다.")

    async def remove_song(self, interaction: discord.Interaction):
        if self.selected_index is not None and self.selected_index < len(list(self.state.queue)):
            song_to_remove = list(self.state.queue)[self.selected_index]
            self.state.queue.remove(song_to_remove)
            await self.update_view(interaction, f"🗑️ '{song_to_remove.title}'을(를) 대기열에서 삭제했습니다.")
    
    async def shuffle(self, interaction: discord.Interaction):
        await self.cog.handle_shuffle(interaction)

    async def clear_queue(self, interaction: discord.Interaction):
        view = ConfirmClearView(self.cog, interaction, self)
        await interaction.response.edit_message(content="정말로 대기열을 모두 비우시겠습니까?", view=view)

    async def update_view(self, interaction: discord.Interaction, message: str, bold_selection: bool = False):
        self.songs = list(self.state.queue)[:25]
        self.build_view()
            
        selected_idx = self.selected_index if bold_selection else None
        embed = self.cog.create_queue_embed(self.state, selected_index=selected_idx)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=message, embed=embed, view=self)
        else:
            await interaction.response.edit_message(content=message, embed=embed, view=self)

class FavoritesSelect(ui.Select):
    def __init__(self, favorites: List[dict]):
        options = [discord.SelectOption(label=f"{fav['title'][:95]}", value=fav['url']) for fav in favorites]
        super().__init__(placeholder="관리할 노래를 선택하세요...", min_values=1, max_values=len(options) if options else 1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_urls = self.values
        await self.view.update_display(interaction)

class FavoritesView(ui.View):
    def __init__(self, cog, interaction: discord.Interaction, favorites: List[dict]):
        super().__init__(timeout=300)
        # 경로 수정
        from .music_utils import BOT_EMBED_COLOR
        self.cog = cog
        self.original_interaction = interaction
        self.user_id = str(interaction.user.id)
        self.favorites = favorites
        self.is_delete_mode = False
        self.selected_urls = []
        self.BOT_EMBED_COLOR = BOT_EMBED_COLOR
        
        self.build_view()

    def create_favorites_embed(self) -> discord.Embed:
        title = "❤️ 즐겨찾기 (삭제 모드)" if self.is_delete_mode else "❤️ 즐겨찾기 (추가 모드)"
        embed = discord.Embed(title=title, color=self.BOT_EMBED_COLOR)
        
        lines = []
        if not self.favorites:
            description = "즐겨찾기 목록이 비어있습니다."
        else:
            for fav in self.favorites:
                line = fav['title']
                if fav['url'] in self.selected_urls:
                    line = f"**✅ {line}**"
                else:
                    line = f"**⬜ {line}**"
                lines.append(line)
            description = "\n".join(lines)
        
        embed.set_footer(text=f"총 {len(self.favorites)}곡 | 선택됨: {len(self.selected_urls)}곡")
        return embed

    def build_view(self):
        self.clear_items()

        if self.favorites:
            self.add_item(FavoritesSelect(self.favorites))
        
        select_all_button = ui.Button(label="전체 선택", style=discord.ButtonStyle.secondary, row=1)
        select_all_button.callback = self.select_all
        deselect_all_button = ui.Button(label="선택 해제", style=discord.ButtonStyle.secondary, row=1, disabled=not self.selected_urls)
        deselect_all_button.callback = self.deselect_all
        self.add_item(select_all_button)
        self.add_item(deselect_all_button)
        
        is_selection_made = bool(self.selected_urls)
        if self.is_delete_mode:
            confirm_button = ui.Button(label="선택한 항목 삭제", style=discord.ButtonStyle.danger, emoji="🗑️", disabled=not is_selection_made, row=2)
            confirm_button.callback = self.delete_selected
            toggle_button = ui.Button(label="추가 모드로 전환", style=discord.ButtonStyle.primary, row=2)
        else:
            confirm_button = ui.Button(label="대기열에 추가", style=discord.ButtonStyle.success, emoji="✅", disabled=not is_selection_made, row=2)
            confirm_button.callback = self.add_selected_to_queue
            toggle_button = ui.Button(label="삭제 모드로 전환", style=discord.ButtonStyle.danger, row=2)
        
        toggle_button.callback = self.toggle_mode
        self.add_item(confirm_button)
        self.add_item(toggle_button)
    
    async def update_display(self, interaction: discord.Interaction):
        self.build_view()
        embed = self.create_favorites_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def toggle_mode(self, interaction: discord.Interaction):
        self.is_delete_mode = not self.is_delete_mode
        await self.update_display(interaction)

    async def select_all(self, interaction: discord.Interaction):
        self.selected_urls = [fav['url'] for fav in self.favorites]
        await self.update_display(interaction)

    async def deselect_all(self, interaction: discord.Interaction):
        self.selected_urls = []
        await self.update_display(interaction)

    async def add_selected_to_queue(self, interaction: discord.Interaction):
        if not self.selected_urls:
            return await interaction.response.send_message("추가할 노래를 선택해주세요.", ephemeral=True)
        
        if not interaction.user.voice:
            return await interaction.response.send_message("음성 채널에 먼저 참여해주세요.", ephemeral=True)

        await interaction.response.defer(thinking=True, ephemeral=True)
        count, joined = await self.cog.handle_add_multiple_from_favorites(interaction, self.selected_urls)
        
        message = f"✅ 즐겨찾기에서 {count}개의 노래를 대기열에 추가했습니다."
        state = await self.cog.get_music_state(interaction.guild.id)
        if state.voice_client and not state.voice_client.is_connected() and count > 0:
             message += "\n음성 채널에 참여하시면 재생이 시작됩니다."
        elif joined:
            message += "\n음성 채널에 자동으로 참가했습니다!"
            
        await interaction.followup.send(message, ephemeral=True)
        try:
            await self.original_interaction.delete_original_response()
        except discord.HTTPException:
            pass
        self.stop()

    async def delete_selected(self, interaction: discord.Interaction):
        if not self.selected_urls:
            return await interaction.response.send_message("삭제할 노래를 선택해주세요.", ephemeral=True)
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        count = await self.cog.handle_delete_from_favorites(self.user_id, self.selected_urls)
        await interaction.followup.send(f"🗑️ 즐겨찾기에서 {count}개의 노래를 삭제했습니다.", ephemeral=True)
        
        try:
            await self.original_interaction.delete_original_response()
        except discord.HTTPException:
            pass
        self.stop()

    async def on_timeout(self):
        try:
            await self.original_interaction.edit_original_response(content="시간이 초과되었습니다.", view=None)
        except discord.HTTPException: pass

class EffectSelect(ui.Select):
    def __init__(self, cog, current_effect: str):
        self.cog = cog
        options = [
            discord.SelectOption(label="효과 없음", value="none", emoji="❌", default=current_effect == "none"),
            discord.SelectOption(label="베이스 부스트", value="bassboost", emoji="🔊", default=current_effect == "bassboost"),
            discord.SelectOption(label="스피드업", value="speedup", emoji="⏩", default=current_effect == "speedup"),
            discord.SelectOption(label="나이트코어", value="nightcore", emoji="🚀", default=current_effect == "nightcore"),
            discord.SelectOption(label="몽환파", value="vaporwave", emoji="🌊", default=current_effect == "vaporwave"),
        ]
        super().__init__(placeholder="🎧 오디오 효과를 선택하세요...", min_values=1, max_values=1, options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_effect_change(interaction, self.values[0])


class MusicPlayerView(ui.View):
    def __init__(self, cog, state):
        super().__init__(timeout=None)
        # 경로 수정
        from .music_utils import LoopMode, LOOP_MODE_DATA
        self.cog, self.state = cog, state
        self.LoopMode = LoopMode
        self.LOOP_MODE_DATA = LOOP_MODE_DATA
        self.create_buttons()

    def create_buttons(self):
        self.clear_items()
        is_paused = self.state.voice_client and self.state.voice_client.is_paused()
        is_playing = self.state.current_song is not None

        play_pause_btn = ui.Button(label="재생" if is_paused else "일시정지", style=discord.ButtonStyle.secondary, emoji="▶️" if is_paused else "⏸️", disabled=not is_playing, row=0)
        play_pause_btn.callback = self.toggle_play_pause
        self.add_item(play_pause_btn)

        skip_btn = ui.Button(label="스킵", style=discord.ButtonStyle.secondary, emoji="⏭️", disabled=not is_playing, row=0)
        skip_btn.callback = self.skip
        self.add_item(skip_btn)

        fav_btn = ui.Button(label="즐찾 추가", style=discord.ButtonStyle.secondary, emoji="⭐", disabled=not is_playing, row=0)
        fav_btn.callback = self.add_to_favorites
        self.add_item(fav_btn)

        leave_btn = ui.Button(label="퇴장", style=discord.ButtonStyle.danger, emoji="🚪", disabled=not self.state.voice_client, row=0)
        leave_btn.callback = self.leave
        self.add_item(leave_btn)

        loop_mode = self.state.loop_mode
        loop_btn = ui.Button(label="반복", style=discord.ButtonStyle.success if loop_mode != self.LoopMode.NONE else discord.ButtonStyle.secondary, emoji=self.LOOP_MODE_DATA[loop_mode][1], row=1)
        loop_btn.callback = self.toggle_loop
        self.add_item(loop_btn)

        auto_play_btn = ui.Button(label="자동재생", style=discord.ButtonStyle.success if self.state.auto_play_enabled else discord.ButtonStyle.secondary, emoji="🎶", row=1)
        auto_play_btn.callback = self.toggle_auto_play
        self.add_item(auto_play_btn)

        queue_btn = ui.Button(label="대기열", style=discord.ButtonStyle.blurple, emoji="📜", row=1)
        queue_btn.callback = self.show_queue
        self.add_item(queue_btn)

        fav_list_btn = ui.Button(label="즐겨찾기", style=discord.ButtonStyle.blurple, emoji="❤️", row=1)
        fav_list_btn.callback = self.show_favorites
        self.add_item(fav_list_btn)

        volume_btn = ui.Button(label="볼륨", style=discord.ButtonStyle.blurple, emoji="🔊", row=1)
        volume_btn.callback = self.open_volume_modal
        self.add_item(volume_btn)
        
        self.add_item(EffectSelect(self.cog, self.state.current_effect))

    async def interaction_check_bot_connected(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("음성 채널에 먼저 참여해주세요.", ephemeral=True)
            return False
            
        state = await self.cog.get_music_state(interaction.guild.id)
        if not state.voice_client or not state.voice_client.is_connected():
             await interaction.response.send_message("봇이 음성 채널에 없습니다.", ephemeral=True)
             return False
        if interaction.user.voice.channel != state.voice_client.channel:
            await interaction.response.send_message("봇과 같은 음성 채널에 있어야 합니다.", ephemeral=True)
            return False
        return True

    async def toggle_play_pause(self, i: discord.Interaction): 
        if await self.interaction_check_bot_connected(i): await self.cog.handle_play_pause(i)
    async def skip(self, i: discord.Interaction): 
        if await self.interaction_check_bot_connected(i): await self.cog.handle_skip(i)
    async def leave(self, i: discord.Interaction): 
        if await self.interaction_check_bot_connected(i): await self.cog.handle_leave(i)
    async def add_to_favorites(self, i: discord.Interaction): 
        if await self.interaction_check_bot_connected(i): await self.cog.handle_add_favorite(i)

    async def toggle_loop(self, i: discord.Interaction): 
        await self.cog.handle_loop(i)
    async def toggle_auto_play(self, i: discord.Interaction):
        await self.cog.handle_toggle_auto_play(i)
    async def show_queue(self, i: discord.Interaction): 
        await self.cog.handle_queue(i)
    async def show_favorites(self, i: discord.Interaction): 
        await self.cog.handle_view_favorites(i)
    async def open_volume_modal(self, i: discord.Interaction):
        state = await self.cog.get_music_state(i.guild.id)
        await i.response.send_modal(VolumeModal(self.cog, state))
