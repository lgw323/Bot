import asyncio
import logging
import os
import random
import time
from collections import deque
from typing import Optional, Any, List, Tuple, Dict
import io
import hashlib
import subprocess
import time as time_lib
from pathlib import Path
from datetime import timedelta
import tempfile # 임시 폴더 사용을 위해 추가

import discord
from discord.ext import commands, tasks
from discord import ui

try:
    from gtts import gTTS
    GTTS_AVAILABLE: bool = True
except ImportError:
    GTTS_AVAILABLE: bool = False
    logging.getLogger(__name__).warning("gTTS 라이브러리를 찾을 수 없습니다.")

from .music_core import MusicState
from .music_utils import (
    Song, LoopMode, LOOP_MODE_DATA, ytdl, URL_REGEX, MUSIC_CHANNEL_ID, MASTER_USER_ID,
    load_favorites, add_favorite, remove_favorites, BOT_EMBED_COLOR,
    load_music_settings, update_music_volume
)
from .music_ui import QueueManagementView, FavoritesView, SearchSelect

logger: logging.Logger = logging.getLogger(__name__)
command_logger: logging.Logger = logging.getLogger("Commands")

class MusicAgentCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        self.music_states: dict = {}
        self.tts_lock: asyncio.Lock = asyncio.Lock()
        
        self.tts_cache_dir: Path = Path(tempfile.gettempdir()) / "bot_tts_cache"
        self.tts_cache_dir.mkdir(parents=True, exist_ok=True)
        self.initial_setup_done: bool = False

    async def cog_load(self) -> None:
        self.update_progress_loop.start()

    async def cog_unload(self) -> None:
        self.update_progress_loop.cancel()
        cleanup_tasks = [state.cleanup(leave=True) for state in self.music_states.values()]
        await asyncio.gather(*cleanup_tasks)

    @tasks.loop(seconds=10)
    async def update_progress_loop(self) -> None:
        for state in self.music_states.values():
            if state.voice_client and state.voice_client.is_connected() and state.voice_client.is_playing():
                await state.schedule_ui_update()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self.initial_setup_done:
            await self.cleanup_tts_cache()
            await self.precache_tts()
            self.initial_setup_done = True
        if MUSIC_CHANNEL_ID == 0:
            return
        for guild in self.bot.guilds:
            await self.get_music_state(guild.id)

    def _get_tts_filepath(self, text: str) -> Path:
        hashed_name = hashlib.sha256(text.encode('utf-8')).hexdigest()
        return self.tts_cache_dir / f"{hashed_name}.opus"

    async def _create_tts_file_if_not_exists(self, text: str) -> bool:
        filepath = self._get_tts_filepath(text)
        if filepath.exists(): return True
        
        try:
            mp3_fp = io.BytesIO()
            tts_obj = gTTS(text=text, lang='ko', slow=False)
            await asyncio.to_thread(tts_obj.write_to_fp, mp3_fp)
            mp3_fp.seek(0)
            mp3_bytes = mp3_fp.read()

            def convert() -> None:
                command = ['ffmpeg', '-i', '-', '-c:a', 'libopus', '-b:a', '32k', '-hide_banner', '-loglevel', 'error', '-y', str(filepath)]
                result = subprocess.run(command, input=mp3_bytes, capture_output=True, check=False)
                if result.returncode != 0:
                    error_message = result.stderr.decode('utf-8')
                    raise RuntimeError(f"FFmpeg failed: {error_message}")
            
            await asyncio.to_thread(convert)
            return True
        except Exception:
            return False

    async def cleanup_tts_cache(self) -> None:
        expiration_time = time_lib.time() - timedelta(days=1).total_seconds()
        for file in self.tts_cache_dir.glob('*.opus'):
            try:
                if file.stat().st_atime < expiration_time:
                    file.unlink()
            except OSError as e: pass

    async def precache_tts(self) -> None:
        tasks = [self._create_tts_file_if_not_exists("노래봇이 입장했습니다.")]
        await asyncio.gather(*tasks)

    def after_tts(self, state: MusicState, was_playing: bool, was_paused: bool) -> None:
        state.is_tts_interrupting = False
        if was_playing:
            if state.voice_client and state.voice_client.is_paused():
                state.voice_client.resume()
        elif not was_paused:
            self.bot.loop.call_soon_threadsafe(state.play_next_song.set)

    async def play_tts(self, state: MusicState, text: str) -> None:
        if not GTTS_AVAILABLE or not state.voice_client or not state.voice_client.is_connected(): return
        
        await self._create_tts_file_if_not_exists(text)
        tts_filepath = self._get_tts_filepath(text)
        if not tts_filepath.exists():
            return

        try: await asyncio.to_thread(os.utime, tts_filepath, None)
        except OSError as e: pass
        
        async with self.tts_lock:
            was_playing = False
            was_paused = False
            try:
                if state.voice_client.is_playing() and state.current_song:
                    was_playing = True
                    state.is_tts_interrupting = True
                    state.voice_client.pause()
                elif state.voice_client.is_paused():
                    was_paused = True
                
                tts_source = discord.FFmpegPCMAudio(str(tts_filepath))
                tts_volume_source = discord.PCMVolumeTransformer(tts_source, volume=2.0)
                state.voice_client.play(tts_volume_source, after=lambda e: self.after_tts(state, was_playing, was_paused))
            except Exception:
                if was_playing and state.voice_client and state.voice_client.is_paused():
                    state.voice_client.resume()
                elif not was_paused:
                    self.bot.loop.call_soon_threadsafe(state.play_next_song.set)
    
    async def get_music_state(self, guild_id: int) -> MusicState:
        if guild_id not in self.music_states:
            guild = self.bot.get_guild(guild_id)
            if not guild: raise RuntimeError(f"Guild with ID {guild_id} not found.")
            
            settings = await load_music_settings()
            guild_settings = settings.get(str(guild_id), {})
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
                        if state.now_playing_message: await state.schedule_ui_update()
                        else:
                             await channel.purge(limit=100, check=lambda m: m.author == self.bot.user)
                             await state.schedule_ui_update()
                    except discord.Forbidden: pass
                    except discord.HTTPException: pass
            
            self.music_states[guild_id] = state
        return self.music_states[guild_id]

    async def cleanup_channel_messages(self, state: MusicState) -> None:
        if not state.text_channel or not state.now_playing_message: return
        if not state.text_channel.permissions_for(state.guild.me).manage_messages: return
        try: 
            await state.text_channel.purge(limit=100, check=lambda msg: msg.id != state.now_playing_message.id and not msg.pinned)
        except discord.HTTPException as e: pass

    async def _ensure_voice_connection(self, user: discord.Member, state: MusicState, send_message_func: Any = None) -> bool:
        if not user.voice or not user.voice.channel:
            if user.id != MASTER_USER_ID:
                if send_message_func:
                    await send_message_func("음성 채널에 먼저 참여해주세요.", ephemeral=True, delete_after=None)
                return False
            if not state.voice_client or not state.voice_client.is_connected():
                if send_message_func:
                    await send_message_func("봇이 현재 음성 채널에 없습니다. 음성 채널에 먼저 참여하거나 봇을 호출해주세요.", ephemeral=True, delete_after=None)
                return False
        return True

    async def _process_play_request(self, guild: discord.Guild, channel: Any, user: discord.Member, query: str, send_message_func: Any) -> None:
        state = await self.get_music_state(guild.id)
        
        if not await self._ensure_voice_connection(user, state, send_message_func):
            return

        is_url = URL_REGEX.match(query)
        task_description = f"`'{query}'`(을)를 처리하는 중..."
        await state.set_task(task_description)

        try:
            if user.voice and user.voice.channel:
                if not state.voice_client or not state.voice_client.is_connected():
                    state.voice_client = await user.voice.channel.connect(timeout=20.0, self_deaf=True)
                elif state.voice_client.channel != user.voice.channel:
                    await state.voice_client.move_to(user.voice.channel)
            
            is_playlist_url = 'list=' in query and is_url
            search_query = query if is_url else f"ytsearch3:{query}"

            data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))

            if is_playlist_url and 'entries' in data:
                state.cancel_autoplay_task()
                entries = data.get('entries', [])
                if not entries:
                    await send_message_func("재생목록을 처리할 수 없거나 비어있습니다.", ephemeral=True, delete_after=5)
                    return

                added_count = 0
                total_songs = len(entries)
                for i, song_data in enumerate(entries):
                    if song_data:
                        song = Song(song_data, user)
                        state.queue.append(song)
                        added_count += 1
                        
                        if (i + 1) % 5 == 0 or (i + 1) == total_songs:
                            await state.set_task(f"🎶 재생목록 추가 중... ({added_count}/{total_songs})")
                
                logger.info(f"[{guild.name}] 재생목록 추가: {added_count}곡")
                command_logger.info(f"사용자 '{user.display_name}'가 '{channel.name}' 채널에서 재생목록을 추가했습니다. (곡 수: {added_count}, URL: {query})")
                await send_message_func(f"✅ 재생목록에서 **{added_count}**개의 노래를 대기열에 추가했습니다.", ephemeral=True, delete_after=5)

            elif 'entries' in data:
                entries = data.get('entries', [])
                if not entries:
                    await send_message_func("노래 정보를 찾을 수 없습니다.", ephemeral=True, delete_after=5)
                    return
                view = ui.View(timeout=180)
                view.add_item(SearchSelect(self, entries))
                await send_message_func("**🔎 검색 결과:**", view=view, ephemeral=True, delete_after=None)
                return

            else:
                song = Song(data, user)
                state.queue.append(song)
                logger.info(f"[{guild.name}] 대기열 추가: '{song.title}'")
                command_logger.info(f"사용자 '{user.display_name}'가 '{channel.name}' 채널에서 노래를 추가했습니다. (제목: '{song.title}', URL: {query})")
                await send_message_func(f"✅ 대기열에 **'{song.title}'** 을(를) 추가했습니다.", ephemeral=True, delete_after=5)

            if state.voice_client and not (state.voice_client.is_playing() or state.voice_client.is_paused()):
                state.play_next_song.set()

        except Exception as e:
            logger.error(f"[{guild.name}] 노래 정보 처리 중 오류", exc_info=True)
            await send_message_func("노래 정보를 가져오는 중 오류가 발생했습니다.", ephemeral=True, delete_after=5)
        finally:
            await state.clear_task()

    async def handle_play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer(ephemeral=True)
        
        music_channel = self.bot.get_channel(MUSIC_CHANNEL_ID)
        if interaction.channel_id != MUSIC_CHANNEL_ID:
            await interaction.followup.send(f"노래 명령어는 {music_channel.mention} 채널에서만 사용할 수 있습니다.", ephemeral=True)
            return

        async def send_msg(content: str, view: Any = discord.utils.MISSING, ephemeral: bool = True, delete_after: Optional[int] = None) -> None:
            await interaction.followup.send(content, view=view, ephemeral=ephemeral)

        await self._process_play_request(interaction.guild, interaction.channel, interaction.user, query, send_msg) # type: ignore

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.channel.id != MUSIC_CHANNEL_ID:
            return
            
        match = URL_REGEX.search(message.content)
        if not match:
            return
            
        url = match.group(0)
        
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        async def send_msg(content: str, view: Any = discord.utils.MISSING, ephemeral: bool = False, delete_after: Optional[int] = None) -> None:
            try:
                if view is not discord.utils.MISSING:
                    await message.channel.send(content, view=view, delete_after=30)
                else:
                    await message.channel.send(content, delete_after=delete_after)
            except discord.HTTPException:
                pass

        await self._process_play_request(message.guild, message.channel, message.author, url, send_msg) # type: ignore

    async def queue_song(self, interaction: discord.Interaction, song_data: dict) -> None:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        state.cancel_autoplay_task()
        song = Song(song_data, interaction.user)
        state.queue.append(song)
        if state.voice_client and not (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.play_next_song.set()
        await state.schedule_ui_update()
        command_logger.info(f"사용자 '{interaction.user.display_name}'가 '{interaction.channel.name}' 채널에서 검색 결과로 노래를 추가했습니다. (제목: '{song.title}')") # type: ignore

    async def handle_skip(self, interaction: discord.Interaction) -> None:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        if state.current_song and state.voice_client:
            state.voice_client.stop()
            await interaction.response.send_message("⏭️ 현재 노래를 건너뛰었습니다.", ephemeral=True, delete_after=5)
            command_logger.info(f"사용자 '{interaction.user.display_name}'가 '{interaction.channel.name}' 채널에서 노래를 스킵했습니다.") # type: ignore
        else: await interaction.response.send_message("건너뛸 노래가 없습니다.", ephemeral=True)

    def create_queue_embed(self, state: MusicState, selected_index: Optional[int] = None) -> discord.Embed:
        embed = discord.Embed(title="🎶 노래 대기열", color=BOT_EMBED_COLOR)
        if state.current_song: embed.add_field(name="현재 재생(일시정지) 중", value=f"[{state.current_song.title}]({state.current_song.webpage_url})", inline=False)
        if not state.queue: queue_text = "비어있음"
        else:
            queue_list = list(state.queue)
            lines = [f"{'**' if i == selected_index else ''}{i+1}. {song.title}{'**' if i == selected_index else ''}" for i, song in enumerate(queue_list[:10])]
            queue_text = "\n".join(lines)
            if len(queue_list) > 10: queue_text += f"\n... 외 {len(queue_list) - 10}곡"
        embed.add_field(name=f"다음 곡 목록 ({len(state.queue)}개)", value=queue_text, inline=False)
        return embed

    async def handle_queue(self, interaction: discord.Interaction) -> None:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        embed = self.create_queue_embed(state)
        view = QueueManagementView(self, state)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def handle_play_pause(self, interaction: discord.Interaction) -> None:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        if state.voice_client and state.current_song:
            if state.voice_client.is_paused():
                state.voice_client.resume()
                if state.pause_start_time:
                    state.total_paused_duration += discord.utils.utcnow() - state.pause_start_time
                    state.pause_start_time = None
                command_logger.info(f"사용자 '{interaction.user.display_name}'가 노래를 재개했습니다.") # type: ignore
            elif state.voice_client.is_playing():
                state.voice_client.pause()
                state.pause_start_time = discord.utils.utcnow()
                command_logger.info(f"사용자 '{interaction.user.display_name}'가 노래를 일시정지했습니다.") # type: ignore
            await state.schedule_ui_update()
            await interaction.response.defer()

    async def handle_loop(self, interaction: discord.Interaction) -> None:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        state.loop_mode = LoopMode((state.loop_mode.value + 1) % 3)
        await state.schedule_ui_update()
        await interaction.response.defer()
        command_logger.info(f"사용자 '{interaction.user.display_name}'가 반복 모드를 '{state.loop_mode.name}'(으)로 변경했습니다.") # type: ignore

    async def handle_toggle_auto_play(self, interaction: discord.Interaction) -> None:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        state.auto_play_enabled = not state.auto_play_enabled
        status = "활성화" if state.auto_play_enabled else "비활성화"
        if not state.auto_play_enabled: state.cancel_autoplay_task()
        await state.schedule_ui_update()
        await interaction.response.send_message(f"🎶 자동 재생을 {status}했습니다.", ephemeral=True, delete_after=5)
        command_logger.info(f"사용자 '{interaction.user.display_name}'가 자동 재생을 {status}했습니다.") # type: ignore

    async def handle_add_favorite(self, interaction: discord.Interaction) -> None:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        if not state.current_song: return await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True) # type: ignore
        song = state.current_song
        user_id = str(interaction.user.id)
        favorites = await load_favorites()
        user_favorites = favorites.get(user_id, [])
        if any(fav['url'] == song.webpage_url for fav in user_favorites): return await interaction.response.send_message("이미 즐겨찾기에 추가된 노래입니다.", ephemeral=True) # type: ignore
        await add_favorite(interaction.user.id, song.webpage_url, song.title)
        await interaction.response.send_message(f"⭐ '{song.title}'을(를) 즐겨찾기에 추가했습니다!", ephemeral=True)
        command_logger.info(f"사용자 '{interaction.user.display_name}'가 '{song.title}'을(를) 즐겨찾기에 추가했습니다.") # type: ignore

    async def handle_view_favorites(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        favorites = await load_favorites()
        user_favorites = favorites.get(user_id, [])
        if not user_favorites: return await interaction.response.send_message("즐겨찾기 목록이 비어있습니다.", ephemeral=True) # type: ignore
        view = FavoritesView(self, interaction, user_favorites)
        embed = view.create_favorites_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def handle_add_multiple_from_favorites(self, interaction: discord.Interaction, urls: List[str]) -> Tuple[int, bool]:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        state.cancel_autoplay_task()
        joined_vc = False
        
        if not await self._ensure_voice_connection(interaction.user, state, None): # type: ignore
            return 0, False
                
        if interaction.user.voice and interaction.user.voice.channel: # type: ignore
            if not state.voice_client or not state.voice_client.is_connected():
                state.voice_client = await interaction.user.voice.channel.connect(timeout=20.0, self_deaf=True) # type: ignore
                joined_vc = True
            elif state.voice_client.channel != interaction.user.voice.channel: # type: ignore
                await state.voice_client.move_to(interaction.user.voice.channel) # type: ignore
                joined_vc = True
        
        count = 0
        total_urls = len(urls)
        await state.set_task(f"❤️ 즐겨찾기에서 `{total_urls}`곡을 추가하는 중...")
        try:
            for i, url in enumerate(urls):
                try:
                    if (i + 1) % 5 == 0 or (i + 1) == total_urls:
                        await state.set_task(f"❤️ 즐겨찾기 추가 중... ({i + 1}/{total_urls})")

                    # [삭제됨] 시간 측정 로직 제거
                    data = await self.bot.loop.run_in_executor(None, lambda target_url=url: ytdl.extract_info(target_url, download=False))
                    # [삭제됨] update_request_timing 호출 제거
                    state.queue.append(Song(data, interaction.user))
                    count += 1
                except Exception as e: logger.warning(f"즐겨찾기 노래 추가 실패 ({url}): {e}")
        finally:
            await state.clear_task()

        if count > 0 and state.voice_client and not (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.play_next_song.set()
        
        command_logger.info(f"사용자 '{interaction.user.display_name}'가 즐겨찾기에서 {count}곡을 대기열에 추가했습니다.") # type: ignore
        
        return count, joined_vc

    async def handle_delete_from_favorites(self, user_id: str, urls_to_delete: List[str]) -> int:
        deleted_count = await remove_favorites(int(user_id), urls_to_delete)
        command_logger.info(f"사용자 ID '{user_id}'가 즐겨찾기에서 {deleted_count}곡을 삭제했습니다.")
        return deleted_count

    async def handle_shuffle(self, interaction: discord.Interaction) -> None:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        if len(state.queue) < 2:
            await interaction.response.send_message("대기열에 섞을 노래가 부족합니다.", ephemeral=True, delete_after=5)
            return
        state.cancel_autoplay_task()
        queue_list = list(state.queue)
        random.shuffle(queue_list)
        state.queue = deque(queue_list)
        await state.schedule_ui_update()
        await interaction.response.send_message("🔀 대기열을 섞었습니다!", ephemeral=True, delete_after=5)
        command_logger.info(f"사용자 '{interaction.user.display_name}'가 대기열을 섞었습니다.") # type: ignore

    async def handle_clear_queue(self, interaction: discord.Interaction, original_interaction: discord.Interaction) -> None:
        state = await self.get_music_state(interaction.guild.id) # type: ignore
        state.cancel_autoplay_task()
        count = len(state.queue)
        state.queue.clear()
        await state.schedule_ui_update()
        await original_interaction.edit_original_response(content=f"🗑️ 대기열의 노래 {count}개를 모두 삭제했습니다.", view=None)
        command_logger.info(f"사용자 '{interaction.user.display_name}'가 대기열을 비웠습니다. ({count}곡 삭제)") # type: ignore

    async def leave_logic(self, guild_id: int) -> None:
        state = self.music_states.pop(guild_id, None)
        if not state: return
        await state.cleanup(leave=True)

    async def handle_leave(self, interaction: discord.Interaction) -> None:
        await self.leave_logic(interaction.guild.id) # type: ignore
        await interaction.response.send_message("🚪 음성 채널에서 퇴장했습니다.", ephemeral=True)
        command_logger.info(f"사용자 '{interaction.user.display_name}'가 봇을 퇴장시켰습니다.") # type: ignore

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.id == self.bot.user.id: # type: ignore
            if not before.channel and after.channel:
                state = self.music_states.get(after.channel.guild.id) # type: ignore
                if state:
                    await asyncio.sleep(1.5)
                    self.bot.loop.create_task(self.play_tts(state, "노래봇이 입장했습니다."))
            if before.channel and not after.channel: await self.leave_logic(before.channel.guild.id) # type: ignore
            return

        state = self.music_states.get(member.guild.id)
        if not state or not state.voice_client or not state.voice_client.is_connected(): return
        bot_channel = state.voice_client.channel
        if before.channel != bot_channel and after.channel == bot_channel:
            user_name = member.display_name
            truncated_name = user_name[:10] + "..." if len(user_name) > 10 else user_name
            if state.current_song and (state.voice_client.is_playing() or state.voice_client.is_paused()):
                state.seek_time = state.get_current_playback_time()
            self.bot.loop.create_task(self.play_tts(state, f"{truncated_name}님이 입장하셨습니다."))
        if before.channel == bot_channel and after.channel != bot_channel and len(bot_channel.members) == 1:
            await asyncio.sleep(2)
            current_state = self.music_states.get(member.guild.id)
            if current_state and current_state.voice_client and current_state.voice_client.is_connected():
                if len(current_state.voice_client.channel.members) == 1: await self.leave_logic(member.guild.id) # type: ignore

async def setup(bot: commands.Bot) -> None:
    if MUSIC_CHANNEL_ID == 0:
        return
    await bot.add_cog(MusicAgentCog(bot))