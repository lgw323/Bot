import asyncio
import logging
import os
import random
from collections import deque
from typing import Optional

import discord
from discord.ext import commands
from discord import ui

# --- gTTS 라이브러리 로드 ---
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logging.getLogger("MusicCog").warning("gTTS 라이브러리를 찾을 수 없습니다. 'pip install gTTS'로 설치해야 TTS 기능을 사용할 수 있습니다.")

# --- 모듈화된 파일에서 클래스와 함수 임포트 ---
from music_core import MusicState
from music_utils import (
    Song, LoopMode, LOOP_MODE_DATA, ytdl, URL_REGEX, MUSIC_CHANNEL_ID,
    load_favorites, save_favorites, BOT_EMBED_COLOR
)
from music_ui import QueueManagementView, FavoritesView, SearchSelect

logger = logging.getLogger("MusicCog")

class MusicAgentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.music_states = {}
        self.tts_lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_ready(self):
        if MUSIC_CHANNEL_ID == 0:
            logger.warning("MUSIC_CHANNEL_ID가 설정되지 않아 상시 플레이어 기능이 비활성화됩니다.")
            return
        
        for guild in self.bot.guilds:
            state = await self.get_music_state(guild.id)
            logger.info(f"'{guild.name}' 서버의 '{state.text_channel.name if state.text_channel else 'N/A'}' 채널에 상시 플레이어를 생성 또는 연결했습니다.")

    def after_tts(self, state: MusicState, interrupted_song: Optional[Song]):
        state.is_tts_interrupting = False # TTS 인터럽트 상태 종료
        try:
            if os.path.exists("tts_temp.mp3"):
                os.remove("tts_temp.mp3")
        except OSError as e:
            logger.error(f"TTS 임시 파일 삭제 실패: {e}")

        if interrupted_song:
            state.queue.appendleft(interrupted_song)

        # TTS가 끝나면 항상 재생 루프를 깨워 다음 곡(또는 첫 곡) 재생을 시도
        self.bot.loop.call_soon_threadsafe(state.play_next_song.set)

    async def play_tts(self, state: MusicState, text: str):
        if not GTTS_AVAILABLE:
            return
        if not state.voice_client or not state.voice_client.is_connected():
            return

        async with self.tts_lock:
            interrupted_song: Optional[Song] = None
            try:
                if (state.voice_client.is_playing() or state.voice_client.is_paused()) and state.current_song:
                    interrupted_song = state.current_song
                    state.is_tts_interrupting = True # TTS 인터럽트 상태 시작
                    state.voice_client.stop()
                    state.play_next_song.clear()

                loop = self.bot.loop
                tts_obj = gTTS(text=text, lang='ko', slow=False)
                await loop.run_in_executor(None, tts_obj.save, "tts_temp.mp3")
                
                tts_source = discord.FFmpegPCMAudio("tts_temp.mp3")
                tts_volume_source = discord.PCMVolumeTransformer(tts_source, volume=2.0)
                
                state.voice_client.play(
                    tts_volume_source, 
                    after=lambda e: self.after_tts(state, interrupted_song)
                )

            except Exception:
                logger.error(f"[{state.guild.name}] TTS 재생 중 오류 발생", exc_info=True)
                if interrupted_song:
                    state.queue.appendleft(interrupted_song)
                self.bot.loop.call_soon_threadsafe(state.play_next_song.set)

    async def get_music_state(self, guild_id: int) -> MusicState:
        if guild_id not in self.music_states:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                raise RuntimeError(f"Guild with ID {guild_id} not found.")

            data = await load_favorites()
            guild_settings = data.get("_guild_settings", {}).get(str(guild_id), {})
            initial_volume = guild_settings.get("volume", 0.5)

            state = MusicState(self.bot, self, guild, initial_volume=initial_volume)

            if MUSIC_CHANNEL_ID != 0:
                channel = self.bot.get_channel(MUSIC_CHANNEL_ID)
                if channel and isinstance(channel, discord.TextChannel) and channel.guild == guild:
                    state.text_channel = channel
                    try:
                        async for message in channel.history(limit=50):
                            if message.author == self.bot.user and message.embeds:
                                state.now_playing_message = message
                                break
                        if state.now_playing_message:
                            await state.update_now_playing_message()
                        else:
                             await channel.purge(limit=100, check=lambda m: m.author == self.bot.user)
                             await state.update_now_playing_message()

                    except discord.Forbidden:
                        logger.warning(f"[{guild.name}] '{channel.name}' 채널의 메시지를 읽거나 삭제할 권한이 없습니다.")
                    except discord.HTTPException:
                        logger.warning(f"[{guild.name}] 플레이어 메시지를 찾는 중 HTTP 오류 발생.")

            self.music_states[guild_id] = state
        return self.music_states[guild_id]


    async def cleanup_channel_messages(self, state: MusicState):
        if not state.text_channel or not state.now_playing_message: return
        if not state.text_channel.permissions_for(state.guild.me).manage_messages: return
        try:
            await state.text_channel.purge(limit=100, check=lambda msg: msg.id != state.now_playing_message.id and not msg.pinned)
        except discord.HTTPException as e:
            logger.debug(f"[{state.guild.name}] 채팅 정리 중 오류: {e}")

    async def handle_play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        music_channel = self.bot.get_channel(MUSIC_CHANNEL_ID)
        if interaction.channel_id != MUSIC_CHANNEL_ID:
            return await interaction.followup.send(f"노래 명령어는 {music_channel.mention} 채널에서만 사용할 수 있습니다.")

        state = await self.get_music_state(interaction.guild.id)

        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.followup.send("음성 채널에 먼저 참여해주세요.", ephemeral=True)
        
        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await interaction.user.voice.channel.connect(timeout=20.0, self_deaf=True)
        elif state.voice_client.channel != interaction.user.voice.channel:
            await state.voice_client.move_to(interaction.user.voice.channel)
        
        try:
            is_playlist_url = 'list=' in query and URL_REGEX.match(query)
            search_query = query if URL_REGEX.match(query) else f"ytsearch3:{query}"

            data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))

            if is_playlist_url and 'entries' in data:
                state.cancel_autoplay_task()
                entries = data.get('entries', [])
                if not entries:
                    await interaction.followup.send("재생목록을 처리할 수 없거나 비어있습니다.")
                    return

                added_count = 0
                for song_data in entries:
                    if song_data:
                        song = Song(song_data, interaction.user)
                        state.queue.append(song)
                        added_count += 1
                
                playlist_title = data.get('title', '이름 없는 재생목록')
                logger.info(f"[{interaction.guild.name}] 재생목록 추가: '{playlist_title}'에서 {added_count}곡 (요청자: {interaction.user.display_name})")
                await interaction.followup.send(f"✅ 재생목록에서 **{added_count}**개의 노래를 대기열에 추가했습니다.")

            elif 'entries' in data:
                entries = data.get('entries', [])
                if not entries:
                    await interaction.followup.send("노래 정보를 찾을 수 없습니다.")
                    return
                view = ui.View(timeout=180)
                view.add_item(SearchSelect(self, entries))
                await interaction.followup.send(content="**🔎 검색 결과:**", view=view, ephemeral=True)
                return

            else:
                song = Song(data, interaction.user)
                state.queue.append(song)
                logger.info(f"[{interaction.guild.name}] 대기열 추가: '{song.title}' (요청자: {interaction.user.display_name})")
                await interaction.followup.send(embed=song.to_embed("✅ 대기열 추가됨: "))

            if state.voice_client and not (state.voice_client.is_playing() or state.voice_client.is_paused()):
                state.play_next_song.set()

            await state.update_now_playing_message()

        except Exception as e:
            logger.error(f"[{interaction.guild.name}] 노래 정보 처리 중 오류", exc_info=True)
            await interaction.followup.send("노래 정보를 가져오는 중 오류가 발생했습니다.")

    async def queue_song(self, interaction: discord.Interaction, song_data: dict):
        state = await self.get_music_state(interaction.guild.id)
        state.cancel_autoplay_task()
        song = Song(song_data, interaction.user)
        state.queue.append(song)
        logger.info(f"[{interaction.guild.name}] 대기열 추가 (검색): '{song.title}' (요청자: {interaction.user.display_name})")
        
        if state.voice_client and not (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.play_next_song.set()
        await state.update_now_playing_message()

    async def handle_skip(self, interaction: discord.Interaction):
        state = await self.get_music_state(interaction.guild.id)
        if state.current_song and state.voice_client:
            logger.info(f"[{interaction.guild.name}] 스킵: '{state.current_song.title}' (요청자: {interaction.user.display_name})")
            state.voice_client.stop()
            await interaction.response.send_message("⏭️ 현재 노래를 건너뛰었습니다.", ephemeral=True, delete_after=5)
        else:
            await interaction.response.send_message("건너뛸 노래가 없습니다.", ephemeral=True)

    def create_queue_embed(self, state: MusicState, selected_index: int = None):
        embed = discord.Embed(title="🎶 노래 대기열", color=BOT_EMBED_COLOR)
        if state.current_song:
            embed.add_field(name="현재 재생(일시정지) 중", value=f"[{state.current_song.title}]({state.current_song.webpage_url})", inline=False)

        if not state.queue:
            queue_text = "비어있음"
        else:
            queue_list = list(state.queue)
            lines = []
            for i, song in enumerate(queue_list[:10]):
                line = f"{i+1}. {song.title}"
                if i == selected_index:
                    line = f"**{line}**"
                lines.append(line)

            queue_text = "\n".join(lines)
            if len(queue_list) > 10:
                queue_text += f"\n... 외 {len(queue_list) - 10}곡"

        embed.add_field(name=f"다음 곡 목록 ({len(state.queue)}개)", value=queue_text, inline=False)
        return embed

    async def handle_queue(self, interaction: discord.Interaction):
        state = await self.get_music_state(interaction.guild.id)
        logger.info(f"[{interaction.guild.name}] 대기열 확인 (요청자: {interaction.user.display_name})")
        embed = self.create_queue_embed(state)
        view = QueueManagementView(self, state)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def handle_volume(self, interaction: discord.Interaction, volume: float):
        state = await self.get_music_state(interaction.guild.id)
        state.volume = max(0.0, min(1.0, volume))
        logger.info(f"[{interaction.guild.name}] 볼륨 변경: {int(state.volume * 100)}% (요청자: {interaction.user.display_name})")
        
        data = await load_favorites()
        guild_id_str = str(interaction.guild.id)

        if "_guild_settings" not in data:
            data["_guild_settings"] = {}
        if guild_id_str not in data["_guild_settings"]:
            data["_guild_settings"][guild_id_str] = {}

        data["_guild_settings"][guild_id_str]['volume'] = state.volume
        await save_favorites(data)

        if state.voice_client and state.voice_client.source:
            if isinstance(state.voice_client.source, discord.PCMVolumeTransformer):
                state.voice_client.source.volume = state.volume

        await state.update_now_playing_message()
        await interaction.response.send_message(f"🔊 볼륨을 {int(state.volume * 100)}%로 조절했습니다.", ephemeral=True)

    async def handle_play_pause(self, interaction: discord.Interaction):
        state = await self.get_music_state(interaction.guild.id)
        if state.voice_client and state.current_song:
            action = "재생" if state.voice_client.is_paused() else "일시정지"
            logger.info(f"[{interaction.guild.name}] {action} (요청자: {interaction.user.display_name})")
            if state.voice_client.is_paused():
                state.voice_client.resume()
                if state.pause_start_time:
                    pause_duration = discord.utils.utcnow() - state.pause_start_time
                    state.total_paused_duration += pause_duration
                    state.pause_start_time = None
            elif state.voice_client.is_playing():
                state.voice_client.pause()
                state.pause_start_time = discord.utils.utcnow()
            await state.update_now_playing_message()
            await interaction.response.defer()

    async def handle_loop(self, interaction: discord.Interaction):
        state = await self.get_music_state(interaction.guild.id)
        current_mode_value = state.loop_mode.value
        next_mode_value = (current_mode_value + 1) % 3
        state.loop_mode = LoopMode(next_mode_value)
        logger.info(f"[{interaction.guild.name}] 반복 모드 변경: {state.loop_mode.name} (요청자: {interaction.user.display_name})")
        await state.update_now_playing_message()
        await interaction.response.defer()

    async def handle_toggle_auto_play(self, interaction: discord.Interaction):
        state = await self.get_music_state(interaction.guild.id)
        state.auto_play_enabled = not state.auto_play_enabled
        status = "활성화" if state.auto_play_enabled else "비활성화"
        logger.info(f"[{interaction.guild.name}] 자동 재생 모드 변경: {status} (요청자: {interaction.user.display_name})")
        
        if not state.auto_play_enabled:
            state.cancel_autoplay_task()

        await state.update_now_playing_message()
        await interaction.response.send_message(f"🎶 자동 재생을 {status}했습니다.", ephemeral=True, delete_after=5)

    async def handle_add_favorite(self, interaction: discord.Interaction):
        state = await self.get_music_state(interaction.guild.id)
        if not state.current_song:
            return await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True)
        song = state.current_song
        user_id = str(interaction.user.id)
        favorites = await load_favorites()
        user_favorites = favorites.get(user_id, [])
        if any(fav['url'] == song.webpage_url for fav in user_favorites):
            return await interaction.response.send_message("이미 즐겨찾기에 추가된 노래입니다.", ephemeral=True)
        user_favorites.append({"title": song.title, "url": song.webpage_url})
        favorites[user_id] = user_favorites
        await save_favorites(favorites)
        logger.info(f"[{interaction.guild.name}] 즐겨찾기 추가: '{song.title}' (사용자: {interaction.user.display_name})")
        await interaction.response.send_message(f"⭐ '{song.title}'을(를) 즐겨찾기에 추가했습니다!", ephemeral=True)

    async def handle_view_favorites(self, interaction: discord.Interaction):
        logger.info(f"[{interaction.guild.name}] 즐겨찾기 목록 확인 (요청자: {interaction.user.display_name})")
        user_id = str(interaction.user.id)
        favorites = await load_favorites()
        user_favorites = favorites.get(user_id, [])
        if not user_favorites:
            return await interaction.response.send_message("즐겨찾기 목록이 비어있습니다.", ephemeral=True)

        view = FavoritesView(self, interaction, user_favorites)
        embed = view.create_favorites_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def handle_add_multiple_from_favorites(self, interaction: discord.Interaction, urls: list[str]) -> tuple[int, bool]:
        state = await self.get_music_state(interaction.guild.id)
        state.cancel_autoplay_task()
        joined_vc = False
        
        if not interaction.user.voice or not interaction.user.voice.channel:
            return 0, False

        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await interaction.user.voice.channel.connect(timeout=20.0, self_deaf=True)
            joined_vc = True
        elif state.voice_client.channel != interaction.user.voice.channel:
            await state.voice_client.move_to(interaction.user.voice.channel)
            joined_vc = True
        
        count = 0
        for url in urls:
            try:
                data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                song = Song(data, interaction.user)
                state.queue.append(song)
                count += 1
            except Exception as e:
                logger.warning(f"즐겨찾기 노래 추가 실패 ({url}): {e}")
        
        logger.info(f"[{interaction.guild.name}] 즐겨찾기에서 {count}곡 추가 (요청자: {interaction.user.display_name})")
        if count > 0 and state.voice_client and not (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.play_next_song.set()

        await state.update_now_playing_message()
        
        return count, joined_vc

    async def handle_delete_from_favorites(self, user_id: str, urls_to_delete: list[str]) -> int:
        favorites = await load_favorites()
        user_favorites = favorites.get(user_id, [])
        if not user_favorites: return 0
        initial_count = len(user_favorites)
        user_favorites = [fav for fav in user_favorites if fav['url'] not in urls_to_delete]
        if not user_favorites:
            if user_id in favorites: del favorites[user_id]
        else: favorites[user_id] = user_favorites
        await save_favorites(favorites)
        deleted_count = initial_count - len(user_favorites)
        logger.info(f"즐겨찾기에서 {deleted_count}곡 삭제 (사용자 ID: {user_id})")
        return deleted_count

    async def handle_shuffle(self, interaction: discord.Interaction):
        state = await self.get_music_state(interaction.guild.id)
        if len(state.queue) < 2:
            await interaction.response.send_message("대기열에 섞을 노래가 부족합니다.", ephemeral=True, delete_after=5)
            return
        state.cancel_autoplay_task()
        queue_list = list(state.queue)
        random.shuffle(queue_list)
        state.queue = deque(queue_list)
        logger.info(f"[{interaction.guild.name}] 대기열 섞음 (요청자: {interaction.user.display_name})")
        await state.update_now_playing_message()
        await interaction.response.send_message("🔀 대기열을 섞었습니다!", ephemeral=True, delete_after=5)

    async def handle_clear_queue(self, interaction: discord.Interaction, original_interaction: discord.Interaction):
        state = await self.get_music_state(interaction.guild.id)
        state.cancel_autoplay_task()
        count = len(state.queue)
        state.queue.clear()
        await state.update_now_playing_message()
        logger.info(f"[{interaction.guild.name}] 대기열의 {count}곡 삭제 (요청자: {interaction.user.display_name})")
        await original_interaction.edit_original_response(content=f"🗑️ 대기열의 노래 {count}개를 모두 삭제했습니다.", view=None)

    async def leave_logic(self, guild_id: int):
        guild_name = self.bot.get_guild(guild_id) or f"ID: {guild_id}"
        
        state = self.music_states.pop(guild_id, None)
        if not state:
            return

        await state.cleanup(leave=True)
        logger.info(f"[{state.guild.name}] 음성 채널 퇴장 및 리소스 정리 완료.")

    async def handle_leave(self, interaction: discord.Interaction):
        logger.info(f"[{interaction.guild.name}] 퇴장 명령 (요청자: {interaction.user.display_name})")
        await self.leave_logic(interaction.guild.id)
        await interaction.response.send_message("🚪 음성 채널에서 퇴장했습니다.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id:
            if not before.channel and after.channel:
                guild_id = after.channel.guild.id
                state = self.music_states.get(guild_id)
                if state:
                    await asyncio.sleep(1.5)
                    self.bot.loop.create_task(self.play_tts(state, "노래봇이 입장했습니다."))
            
            if before.channel and not after.channel:
                await self.leave_logic(before.channel.guild.id)
            return

        state = self.music_states.get(member.guild.id)
        if not state or not state.voice_client or not state.voice_client.is_connected():
            return

        bot_channel = state.voice_client.channel

        user_joined_bot_channel = before.channel != bot_channel and after.channel == bot_channel
        if user_joined_bot_channel:
            MAX_NICKNAME_LENGTH = 10
            user_name = member.display_name
            if len(user_name) > MAX_NICKNAME_LENGTH:
                truncated_name = user_name[:MAX_NICKNAME_LENGTH] + "..."
            else:
                truncated_name = user_name
            tts_text = f"{truncated_name}님이 입장하셨습니다."
            
            if state.current_song and (state.voice_client.is_playing() or state.voice_client.is_paused()):
                current_timestamp = state.get_current_playback_time()
                state.seek_time = current_timestamp
            
            self.bot.loop.create_task(self.play_tts(state, tts_text))

        user_left_bot_channel = before.channel == bot_channel and after.channel != bot_channel
        is_bot_now_alone = len(bot_channel.members) == 1 and self.bot.user in bot_channel.members
        
        if user_left_bot_channel and is_bot_now_alone:
            await asyncio.sleep(2)

            current_state = self.music_states.get(member.guild.id)
            if current_state and current_state.voice_client and current_state.voice_client.is_connected():
                bot_channel_after_wait = current_state.voice_client.channel
                if len(bot_channel_after_wait.members) == 1:
                    await self.leave_logic(member.guild.id)

    async def handle_effect_change(self, interaction: discord.Interaction, effect: str):
        state = await self.get_music_state(interaction.guild.id)
        logger.info(f"[{interaction.guild.name}] 오디오 효과 변경: '{state.current_effect}' -> '{effect}' (요청자: {interaction.user.display_name})")

        if state.current_song and state.voice_client and interaction.user.voice and interaction.user.voice.channel == state.voice_client.channel:
            if state.current_effect == effect:
                return await interaction.response.defer()

            current_timestamp = state.get_current_playback_time()
            
            state.seek_time = current_timestamp
            state.current_effect = effect
            
            state.queue.appendleft(state.current_song)
            state.voice_client.stop()
            
            await interaction.response.send_message(f"🎧 효과를 **{effect.capitalize()}**(으)로 즉시 변경합니다.", ephemeral=True, delete_after=5)
        else:
            state.current_effect = effect
            await state.update_now_playing_message()
            await interaction.response.send_message(f"🎧 다음 곡부터 **'{effect.capitalize()}'** 효과가 적용됩니다.", ephemeral=True)


async def setup(bot: commands.Bot):
    if MUSIC_CHANNEL_ID == 0:
        logger.error("환경변수에 MUSIC_CHANNEL_ID가 설정되지 않았습니다! music_agent를 로드하지 않습니다.")
        return
    await bot.add_cog(MusicAgentCog(bot))
