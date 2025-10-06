import asyncio
import logging
import os
import random
import time
import statistics
from collections import deque
from typing import Optional

import hashlib
import subprocess
import time as time_lib
from pathlib import Path
from datetime import timedelta

import discord
from discord.ext import commands
from discord import ui

# gTTS 라이브러리가 설치되어 있는지 확인하고, 없으면 경고 메시지를 출력합니다.
# TTS(Text-to-Speech) 기능에 필요합니다.
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logging.getLogger("MusicCog").warning("gTTS 라이브러리를 찾을 수 없습니다. 'pip install gTTS'로 설치해야 TTS 기능을 사용할 수 있습니다.")

# 다른 모듈에서 필요한 클래스와 함수들을 가져옵니다.
from .music_core import MusicState
from .music_utils import (
    Song, LoopMode, LOOP_MODE_DATA, ytdl, URL_REGEX, MUSIC_CHANNEL_ID,
    load_favorites, save_favorites, BOT_EMBED_COLOR,
    load_music_settings, save_music_settings, update_request_timing
)
from .music_ui import QueueManagementView, FavoritesView, SearchSelect

# 이 파일에서 사용할 로거(기록기)를 설정합니다.
logger = logging.getLogger("MusicCog")

class MusicAgentCog(commands.Cog):
    """
    음악 재생과 관련된 모든 상호작용 및 이벤트 처리를 담당하는 Cog입니다.
    사용자의 명령어를 받아 MusicState를 제어하고, TTS, 캐시 관리 등의 부가 기능을 수행합니다.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.music_states = {}  # 서버(Guild)별 음악 상태를 저장하는 딕셔너리
        self.tts_lock = asyncio.Lock()  # TTS 파일 생성 시 동시 접근을 막기 위한 잠금 장치
        self.tts_cache_dir = Path("data/tts_cache")  # TTS 오디오 파일을 저장할 폴더 경로
        self.tts_cache_dir.mkdir(parents=True, exist_ok=True)
        self.initial_setup_done = False  # 봇 초기 설정 완료 여부 플래그

    async def cog_unload(self):
        """Cog가 비활성화될 때 호출되는 함수. 모든 음악 재생 상태를 정리합니다."""
        logger.info("MusicAgentCog 언로드 시작... 모든 활성 MusicState를 정리합니다.")
        cleanup_tasks = [state.cleanup(leave=True) for state in self.music_states.values()]
        await asyncio.gather(*cleanup_tasks)
        logger.info("모든 MusicState 정리 완료.")

    @commands.Cog.listener()
    async def on_ready(self):
        """봇이 준비되었을 때 한 번 실행되는 이벤트 리스너입니다."""
        if not self.initial_setup_done:
            # TTS 캐시 정리 및 사전 생성을 수행합니다.
            logger.info("[TTS Cache] 초기 설정을 시작합니다...")
            await self.cleanup_tts_cache()
            await self.precache_tts()
            self.initial_setup_done = True
            logger.info("[TTS Cache] 초기 설정을 완료했습니다.")
        
        # MUSIC_CHANNEL_ID가 설정되지 않았으면 상시 플레이어 기능을 사용하지 않습니다.
        if MUSIC_CHANNEL_ID == 0:
            logger.warning("MUSIC_CHANNEL_ID가 설정되지 않아 상시 플레이어 기능이 비활성화됩니다.")
            return
        
        # 봇이 속한 모든 서버에 대해 상시 플레이어를 설정합니다.
        for guild in self.bot.guilds:
            state = await self.get_music_state(guild.id)
            logger.info(f"'{guild.name}' 서버의 '{state.text_channel.name if state.text_channel else 'N/A'}' 채널에 상시 플레이어를 생성 또는 연결했습니다.")

    def _get_tts_filepath(self, text: str) -> Path:
        """TTS로 변환할 텍스트를 해시하여 고유한 파일 경로를 생성합니다."""
        hashed_name = hashlib.sha256(text.encode('utf-8')).hexdigest()
        return self.tts_cache_dir / f"{hashed_name}.opus"

    async def _create_tts_file_if_not_exists(self, text: str):
        """TTS 오디오 파일이 없으면 새로 생성합니다."""
        filepath = self._get_tts_filepath(text)
        if filepath.exists(): return True # 이미 파일이 있으면 생성하지 않음
        
        logger.info(f"[TTS Cache] 신규 캐시 파일 생성: '{text}'")
        temp_mp3_path = self.tts_cache_dir / f"temp_{os.urandom(8).hex()}.mp3"
        try:
            # gTTS를 사용하여 텍스트를 mp3 파일로 변환
            tts_obj = gTTS(text=text, lang='ko', slow=False)
            await asyncio.to_thread(tts_obj.save, str(temp_mp3_path))
            
            # FFmpeg를 사용하여 mp3를 디스코드가 지원하는 opus 형식으로 변환
            def convert():
                command = ['ffmpeg', '-i', str(temp_mp3_path), '-c:a', 'libopus', '-b:a', '32k', '-hide_banner', '-loglevel', 'error', str(filepath)]
                result = subprocess.run(command, capture_output=True, text=True)
                if result.returncode != 0: raise RuntimeError(f"FFmpeg failed: {result.stderr}")
            await asyncio.to_thread(convert)
            return True
        except Exception:
            logger.error(f"[TTS Cache] TTS 파일 생성 실패: '{text}'", exc_info=True)
            return False
        finally:
            # 임시 mp3 파일 삭제
            if temp_mp3_path.exists(): temp_mp3_path.unlink()

    async def cleanup_tts_cache(self):
        """오래된 TTS 캐시 파일을 주기적으로 삭제합니다."""
        logger.info("[TTS Cache] 3일 이상된 캐시 파일 정리를 시작합니다...")
        pruned_count = 0
        expiration_time = time_lib.time() - timedelta(days=3).total_seconds()
        for file in self.tts_cache_dir.glob('*.opus'):
            try:
                if file.stat().st_atime < expiration_time:
                    file.unlink()
                    pruned_count += 1
            except OSError as e: logger.warning(f"[TTS Cache] 파일 삭제 실패 {file}: {e}")
        logger.info(f"[TTS Cache] 정리 완료. {pruned_count}개의 오래된 파일을 삭제했습니다.")

    async def precache_tts(self):
        """자주 사용될 TTS 음성(예: 멤버 입장)을 미리 캐싱하여 응답 속도를 높입니다."""
        logger.info("[TTS Cache] 멤버 입장 음성 사전 캐싱을 시작합니다...")
        tasks = [self._create_tts_file_if_not_exists("노래봇이 입장했습니다.")]
        for guild in self.bot.guilds:
            for member in guild.members:
                if member.bot: continue
                user_name = member.display_name
                truncated_name = user_name[:10] + "..." if len(user_name) > 10 else user_name
                tasks.append(self._create_tts_file_if_not_exists(f"{truncated_name}님이 입장하셨습니다."))
        await asyncio.gather(*tasks)
        logger.info(f"[TTS Cache] 사전 캐싱 완료. {len(tasks)}개의 음성을 확인/생성했습니다.")

    def after_tts(self, state: MusicState, interrupted_song: Optional[Song]):
        """TTS 재생이 끝난 후 호출되는 콜백 함수. 중단되었던 노래를 다시 재생 큐에 넣습니다."""
        state.is_tts_interrupting = False
        if interrupted_song: state.queue.appendleft(interrupted_song) # 중단된 노래를 큐의 맨 앞에 다시 추가
        self.bot.loop.call_soon_threadsafe(state.play_next_song.set)

    async def play_tts(self, state: MusicState, text: str):
        """주어진 텍스트를 음성으로 변환하여 재생합니다."""
        if not GTTS_AVAILABLE or not state.voice_client or not state.voice_client.is_connected(): return
        
        await self._create_tts_file_if_not_exists(text)
        tts_filepath = self._get_tts_filepath(text)
        if not tts_filepath.exists():
            logger.error(f"TTS 파일 재생 실패: '{text}' 파일이 생성되지 않았습니다.")
            return

        try: await asyncio.to_thread(os.utime, tts_filepath, None) # 파일 접근 시간 갱신
        except OSError as e: logger.warning(f"파일 접근 시간 갱신 실패 {tts_filepath}: {e}")
        
        async with self.tts_lock:
            interrupted_song: Optional[Song] = None
            try:
                # 노래가 재생 중이었다면, 현재 노래를 잠시 중단하고 기억해둡니다.
                if (state.voice_client.is_playing() or state.voice_client.is_paused()) and state.current_song:
                    interrupted_song = state.current_song
                    state.is_tts_interrupting = True
                    state.voice_client.stop()
                    state.play_next_song.clear()
                
                # TTS 오디오 소스를 생성하고 재생합니다.
                tts_source = discord.FFmpegPCMAudio(str(tts_filepath))
                tts_volume_source = discord.PCMVolumeTransformer(tts_source, volume=2.0)
                state.voice_client.play(tts_volume_source, after=lambda e: self.after_tts(state, interrupted_song))
                logger.info(f"[TTS Cache] 캐시된 파일 재생: '{text}'")
            except Exception:
                logger.error(f"[{state.guild.name}] TTS 재생 중 오류 발생", exc_info=True)
                if interrupted_song: state.queue.appendleft(interrupted_song)
                self.bot.loop.call_soon_threadsafe(state.play_next_song.set)
    
    async def get_music_state(self, guild_id: int) -> MusicState:
        """
        서버(Guild) ID를 기반으로 MusicState 객체를 가져오거나 새로 생성합니다.
        MusicState는 서버별 음악 재생 상태(큐, 볼륨, 현재 곡 등)를 관리합니다.
        """
        if guild_id not in self.music_states:
            guild = self.bot.get_guild(guild_id)
            if not guild: raise RuntimeError(f"Guild with ID {guild_id} not found.")
            
            # 저장된 설정에서 초기 볼륨 값을 불러옵니다.
            settings = await load_music_settings()
            guild_settings = settings.get(str(guild_id), {})
            initial_volume = guild_settings.get("volume", 0.5)
            
            # 새로운 MusicState 객체 생성
            state = MusicState(self.bot, self, guild, initial_volume=initial_volume)
            
            # 상시 플레이어가 표시될 채널을 설정하고, 기존 메시지가 있는지 확인합니다.
            if MUSIC_CHANNEL_ID != 0:
                channel = self.bot.get_channel(MUSIC_CHANNEL_ID)
                if channel and isinstance(channel, discord.TextChannel) and channel.guild == guild:
                    state.text_channel = channel
                    try:
                        # 채널의 최근 메시지를 확인하여 봇이 보낸 플레이어 메시지를 찾습니다.
                        async for message in channel.history(limit=50):
                            if message.author == self.bot.user and message.embeds:
                                state.now_playing_message = message
                                break
                        # 기존 메시지를 찾았으면 UI를 업데이트하고, 없으면 새로 만듭니다.
                        if state.now_playing_message: await state.schedule_ui_update()
                        else:
                             await channel.purge(limit=100, check=lambda m: m.author == self.bot.user)
                             await state.schedule_ui_update()
                    except discord.Forbidden: logger.warning(f"[{guild.name}] '{channel.name}' 채널의 메시지를 읽거나 삭제할 권한이 없습니다.")
                    except discord.HTTPException: logger.warning(f"[{guild.name}] 플레이어 메시지를 찾는 중 HTTP 오류 발생.")
            
            self.music_states[guild_id] = state
        return self.music_states[guild_id]

    async def cleanup_channel_messages(self, state: MusicState):
        """음악 채널의 불필요한 메시지를 정리하여 플레이어 UI만 남도록 합니다."""
        if not state.text_channel or not state.now_playing_message: return
        if not state.text_channel.permissions_for(state.guild.me).manage_messages: return
        try: 
            await state.text_channel.purge(limit=100, check=lambda msg: msg.id != state.now_playing_message.id and not msg.pinned)
        except discord.HTTPException as e: 
            logger.debug(f"[{state.guild.name}] 채팅 정리 중 오류: {e}")

    async def handle_play(self, interaction: discord.Interaction, query: str):
        """
        /재생 명령어의 핵심 로직을 처리합니다.
        사용자의 상호작용을 받아 노래를 검색하거나 URL을 처리하여 큐에 추가합니다.
        """
        # defer()는 "생각 중..." 메시지를 보내는 중요한 함수입니다.
        # 3초 이상 걸리는 작업 전에 반드시 호출해야 상호작용 실패를 막을 수 있습니다.
        await interaction.response.defer(ephemeral=True)
        
        music_channel = self.bot.get_channel(MUSIC_CHANNEL_ID)
        if interaction.channel_id != MUSIC_CHANNEL_ID:
            await interaction.followup.send(f"노래 명령어는 {music_channel.mention} 채널에서만 사용할 수 있습니다.", ephemeral=True)
            return

        state = await self.get_music_state(interaction.guild.id)
        
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("음성 채널에 먼저 참여해주세요.", ephemeral=True)
            return
        
        settings = await load_music_settings()
        is_url = URL_REGEX.match(query)
        task_type = 'url' if is_url else 'search'
        
        # 이전 요청들의 평균 처리 시간을 계산하여 사용자에게 예상 시간을 알려줍니다.
        timings_history = settings.get(str(interaction.guild.id), {}).get("request_timings", {}).get(task_type, [])
        avg_time_ms = statistics.mean(timings_history) if len(timings_history) > 1 else 2000

        task_description = f"`'{query}'`(을)를 처리하는 중...\n_(예상 시간: 약 {avg_time_ms / 1000:.1f}초)_"
        await state.set_task(task_description) # 메인 플레이어 UI에 작업 상태를 표시

        try:
            # 봇이 음성 채널에 없으면 입장시키고, 다른 채널에 있으면 이동시킵니다.
            if not state.voice_client or not state.voice_client.is_connected():
                state.voice_client = await interaction.user.voice.channel.connect(timeout=20.0, self_deaf=True)
            elif state.voice_client.channel != interaction.user.voice.channel:
                await state.voice_client.move_to(interaction.user.voice.channel)
            
            start_time = time.monotonic()
            
            is_playlist_url = 'list=' in query and is_url
            search_query = query if is_url else f"ytsearch3:{query}"

            # yt-dlp를 사용하여 유튜브에서 노래 정보를 가져옵니다. (시간이 오래 걸리는 작업)
            data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))

            # 실제 처리 시간을 기록하여 다음 예상 시간 계산에 사용합니다.
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await update_request_timing(interaction.guild.id, task_type, duration_ms)

            # --- 처리 결과에 따라 분기 ---
            
            # 1. 재생목록(Playlist) URL인 경우
            if is_playlist_url and 'entries' in data:
                state.cancel_autoplay_task()
                entries = data.get('entries', [])
                if not entries:
                    await interaction.followup.send("재생목록을 처리할 수 없거나 비어있습니다.", ephemeral=True)
                    return

                added_count = 0
                for song_data in entries:
                    if song_data:
                        song = Song(song_data, interaction.user)
                        state.queue.append(song)
                        added_count += 1
                
                logger.info(f"[{interaction.guild.name}] 재생목록 추가: {added_count}곡 (요청자: {interaction.user.display_name})")
                # 최종 응답을 보내 "생각 중..." 메시지를 대체합니다.
                await interaction.followup.send(f"✅ 재생목록에서 **{added_count}**개의 노래를 대기열에 추가했습니다.", ephemeral=True)

            # 2. 검색어인 경우 (결과가 여러 개)
            elif 'entries' in data:
                entries = data.get('entries', [])
                if not entries:
                    await interaction.followup.send("노래 정보를 찾을 수 없습니다.", ephemeral=True)
                    return
                # 사용자에게 선택지를 제공하는 UI를 보냅니다.
                view = ui.View(timeout=180)
                view.add_item(SearchSelect(self, entries))
                await interaction.followup.send("**🔎 검색 결과:**", view=view, ephemeral=True)
                return # 여기서 함수를 종료해야 아래 코드가 실행되지 않습니다.

            # 3. 단일 곡 URL인 경우
            else:
                song = Song(data, interaction.user)
                state.queue.append(song)
                logger.info(f"[{interaction.guild.name}] 대기열 추가: '{song.title}' (요청자: {interaction.user.display_name})")

                # --- [수정된 부분] ---
                # 이 부분이 바로 누락되었던 최종 응답 코드입니다.
                # 이 코드가 없어서 "생각 중..." 메시지가 사라지지 않았습니다.
                await interaction.followup.send(f"✅ 대기열에 **'{song.title}'** 을(를) 추가했습니다.", ephemeral=True)


            # 노래 큐에 노래가 추가되었고, 현재 재생 중이 아니라면 재생을 시작합니다.
            if state.voice_client and not (state.voice_client.is_playing() or state.voice_client.is_paused()):
                state.play_next_song.set()

        except Exception as e:
            logger.error(f"[{interaction.guild.name}] 노래 정보 처리 중 오류", exc_info=True)
            await interaction.followup.send("노래 정보를 가져오는 중 오류가 발생했습니다.", ephemeral=True)
        finally:
            await state.clear_task() # 메인 플레이어 UI의 작업 상태 표시를 지웁니다.

    async def queue_song(self, interaction: discord.Interaction, song_data: dict):
        """검색 결과에서 사용자가 선택한 노래를 큐에 추가합니다."""
        state = await self.get_music_state(interaction.guild.id)
        state.cancel_autoplay_task()
        song = Song(song_data, interaction.user)
        state.queue.append(song)
        logger.info(f"[{interaction.guild.name}] 대기열 추가 (검색): '{song.title}' (요청자: {interaction.user.display_name})")
        if state.voice_client and not (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.play_next_song.set()
        await state.schedule_ui_update()

    async def handle_skip(self, interaction: discord.Interaction):
        """현재 노래를 건너뛰는 상호작용을 처리합니다."""
        state = await self.get_music_state(interaction.guild.id)
        if state.current_song and state.voice_client:
            logger.info(f"[{interaction.guild.name}] 스킵: '{state.current_song.title}' (요청자: {interaction.user.display_name})")
            state.voice_client.stop() # 노래를 멈추면 자동으로 다음 곡이 재생됩니다.
            await interaction.response.send_message("⏭️ 현재 노래를 건너뛰었습니다.", ephemeral=True, delete_after=5)
        else:
            await interaction.response.send_message("건너뛸 노래가 없습니다.", ephemeral=True)

    def create_queue_embed(self, state: MusicState, selected_index: int = None):
        """현재 대기열 상태를 보여주는 Embed 메시지를 생성합니다."""
        embed = discord.Embed(title="🎶 노래 대기열", color=BOT_EMBED_COLOR)
        if state.current_song: 
            embed.add_field(name="현재 재생(일시정지) 중", value=f"[{state.current_song.title}]({state.current_song.webpage_url})", inline=False)
        
        if not state.queue:
            queue_text = "비어있음"
        else:
            queue_list = list(state.queue)
            lines = [f"{'**' if i == selected_index else ''}{i+1}. {song.title}{'**' if i == selected_index else ''}" for i, song in enumerate(queue_list[:10])]
            queue_text = "\n".join(lines)
            if len(queue_list) > 10:
                queue_text += f"\n... 외 {len(queue_list) - 10}곡"
        
        embed.add_field(name=f"다음 곡 목록 ({len(state.queue)}개)", value=queue_text, inline=False)
        return embed

    async def handle_queue(self, interaction: discord.Interaction):
        """'대기열' 버튼 상호작용을 처리하여 대기열 UI를 보여줍니다."""
        state = await self.get_music_state(interaction.guild.id)
        logger.info(f"[{interaction.guild.name}] 대기열 확인 (요청자: {interaction.user.display_name})")
        embed = self.create_queue_embed(state)
        view = QueueManagementView(self, state)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def handle_play_pause(self, interaction: discord.Interaction):
        """재생/일시정지 버튼 상호작용을 처리합니다."""
        state = await self.get_music_state(interaction.guild.id)
        if state.voice_client and state.current_song:
            action = "재생" if state.voice_client.is_paused() else "일시정지"
            logger.info(f"[{interaction.guild.name}] {action} (요청자: {interaction.user.display_name})")
            if state.voice_client.is_paused():
                state.voice_client.resume()
                if state.pause_start_time:
                    state.total_paused_duration += discord.utils.utcnow() - state.pause_start_time
                    state.pause_start_time = None
            elif state.voice_client.is_playing():
                state.voice_client.pause()
                state.pause_start_time = discord.utils.utcnow()
            await state.schedule_ui_update()
            await interaction.response.defer() # 버튼 클릭에 대한 응답 (아무것도 안 보냄)

    async def handle_loop(self, interaction: discord.Interaction):
        """반복 모드 변경 버튼 상호작용을 처리합니다."""
        state = await self.get_music_state(interaction.guild.id)
        state.loop_mode = LoopMode((state.loop_mode.value + 1) % 3)
        logger.info(f"[{interaction.guild.name}] 반복 모드 변경: {state.loop_mode.name} (요청자: {interaction.user.display_name})")
        await state.schedule_ui_update()
        await interaction.response.defer()

    async def handle_toggle_auto_play(self, interaction: discord.Interaction):
        """자동 재생 활성화/비활성화 버튼 상호작용을 처리합니다."""
        state = await self.get_music_state(interaction.guild.id)
        state.auto_play_enabled = not state.auto_play_enabled
        status = "활성화" if state.auto_play_enabled else "비활성화"
        logger.info(f"[{interaction.guild.name}] 자동 재생 모드 변경: {status} (요청자: {interaction.user.display_name})")
        if not state.auto_play_enabled: state.cancel_autoplay_task()
        await state.schedule_ui_update()
        await interaction.response.send_message(f"🎶 자동 재생을 {status}했습니다.", ephemeral=True, delete_after=5)

    async def handle_add_favorite(self, interaction: discord.Interaction):
        """즐겨찾기 추가 버튼 상호작용을 처리합니다."""
        state = await self.get_music_state(interaction.guild.id)
        if not state.current_song:
            return await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True)
        song = state.current_song
        user_id = str(interaction.user.id)
        favorites = await load_favorites()
        user_favorites = favorites.setdefault(user_id, [])
        if any(fav['url'] == song.webpage_url for fav in user_favorites):
            return await interaction.response.send_message("이미 즐겨찾기에 추가된 노래입니다.", ephemeral=True)
        user_favorites.append({"title": song.title, "url": song.webpage_url})
        await save_favorites(favorites)
        logger.info(f"[{interaction.guild.name}] 즐겨찾기 추가: '{song.title}' (사용자: {interaction.user.display_name})")
        await interaction.response.send_message(f"⭐ '{song.title}'을(를) 즐겨찾기에 추가했습니다!", ephemeral=True)

    async def handle_view_favorites(self, interaction: discord.Interaction):
        """즐겨찾기 목록 보기 버튼 상호작용을 처리합니다."""
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
        """즐겨찾기 목록에서 여러 곡을 한 번에 큐에 추가합니다."""
        state = await self.get_music_state(interaction.guild.id)
        state.cancel_autoplay_task()
        joined_vc = False
        if not interaction.user.voice or not interaction.user.voice.channel: return 0, False

        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await interaction.user.voice.channel.connect(timeout=20.0, self_deaf=True)
            joined_vc = True
        elif state.voice_client.channel != interaction.user.voice.channel:
            await state.voice_client.move_to(interaction.user.voice.channel)
            joined_vc = True
        
        await state.set_task(f"❤️ 즐겨찾기에서 `{len(urls)}`곡을 추가하는 중...")
        count = 0
        try:
            for url in urls:
                try:
                    start_time = time.monotonic()
                    data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    await update_request_timing(interaction.guild.id, 'favorites', duration_ms)
                    state.queue.append(Song(data, interaction.user))
                    count += 1
                except Exception as e: logger.warning(f"즐겨찾기 노래 추가 실패 ({url}): {e}")
        finally:
            await state.clear_task()

        logger.info(f"[{interaction.guild.name}] 즐겨찾기에서 {count}곡 추가 (요청자: {interaction.user.display_name})")
        if count > 0 and state.voice_client and not (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.play_next_song.set()
        
        return count, joined_vc

    async def handle_delete_from_favorites(self, user_id: str, urls_to_delete: list[str]) -> int:
        """즐겨찾기에서 선택한 노래들을 삭제합니다."""
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
        """대기열을 무작위로 섞습니다."""
        state = await self.get_music_state(interaction.guild.id)
        if len(state.queue) < 2:
            await interaction.response.send_message("대기열에 섞을 노래가 부족합니다.", ephemeral=True, delete_after=5)
            return
        state.cancel_autoplay_task()
        queue_list = list(state.queue)
        random.shuffle(queue_list)
        state.queue = deque(queue_list)
        logger.info(f"[{interaction.guild.name}] 대기열 섞음 (요청자: {interaction.user.display_name})")
        await state.schedule_ui_update()
        await interaction.response.send_message("🔀 대기열을 섞었습니다!", ephemeral=True, delete_after=5)

    async def handle_clear_queue(self, interaction: discord.Interaction, original_interaction: discord.Interaction):
        """대기열의 모든 노래를 삭제합니다."""
        state = await self.get_music_state(interaction.guild.id)
        state.cancel_autoplay_task()
        count = len(state.queue)
        state.queue.clear()
        await state.schedule_ui_update()
        logger.info(f"[{interaction.guild.name}] 대기열의 {count}곡 삭제 (요청자: {interaction.user.display_name})")
        await original_interaction.edit_original_response(content=f"🗑️ 대기열의 노래 {count}개를 모두 삭제했습니다.", view=None)

    async def leave_logic(self, guild_id: int):
        """봇을 음성 채널에서 퇴장시키고 관련 리소스를 정리하는 내부 로직입니다."""
        state = self.music_states.pop(guild_id, None)
        if not state: return
        await state.cleanup(leave=True)
        logger.info(f"[{state.guild.name}] 음성 채널 퇴장 및 리소스 정리 완료.")

    async def handle_leave(self, interaction: discord.Interaction):
        """퇴장 버튼 상호작용을 처리합니다."""
        logger.info(f"[{interaction.guild.name}] 퇴장 명령 (요청자: {interaction.user.display_name})")
        await self.leave_logic(interaction.guild.id)
        await interaction.response.send_message("🚪 음성 채널에서 퇴장했습니다.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """
        음성 채널 상태 변경(참여, 퇴장, 이동 등)을 감지하는 이벤트 리스너입니다.
        봇 입장/퇴장, 유저 입장 안내, 자동 퇴장 등의 기능을 처리합니다.
        """
        # 봇 자신의 상태 변경 감지
        if member.id == self.bot.user.id:
            if not before.channel and after.channel: # 봇이 음성 채널에 입장했을 때
                state = self.music_states.get(after.channel.guild.id)
                if state:
                    await asyncio.sleep(1.5)
                    self.bot.loop.create_task(self.play_tts(state, "노래봇이 입장했습니다."))
            if before.channel and not after.channel: # 봇이 음성 채널에서 퇴장했을 때
                await self.leave_logic(before.channel.guild.id)
            return

        # 사용자의 상태 변경 감지
        state = self.music_states.get(member.guild.id)
        if not state or not state.voice_client or not state.voice_client.is_connected(): return
        
        bot_channel = state.voice_client.channel
        
        # 사용자가 봇이 있는 채널에 입장했을 때
        if before.channel != bot_channel and after.channel == bot_channel:
            user_name = member.display_name
            truncated_name = user_name[:10] + "..." if len(user_name) > 10 else user_name
            if state.current_song and (state.voice_client.is_playing() or state.voice_client.is_paused()):
                state.seek_time = state.get_current_playback_time()
            self.bot.loop.create_task(self.play_tts(state, f"{truncated_name}님이 입장하셨습니다."))
        
        # 봇과 유저만 있던 채널에서 유저가 나갔을 때 (자동 퇴장 로직)
        if before.channel == bot_channel and after.channel != bot_channel and len(bot_channel.members) == 1:
            await asyncio.sleep(2) # 혹시 바로 다른 유저가 들어올 수 있으므로 잠시 대기
            current_state = self.music_states.get(member.guild.id)
            if current_state and current_state.voice_client and current_state.voice_client.is_connected():
                if len(current_state.voice_client.channel.members) == 1: # 2초 후에도 여전히 봇 혼자라면 퇴장
                    await self.leave_logic(member.guild.id)

    async def handle_effect_change(self, interaction: discord.Interaction, effect: str):
        """오디오 효과 변경 상호작용을 처리합니다."""
        state = await self.get_music_state(interaction.guild.id)
        logger.info(f"[{interaction.guild.name}] 오디오 효과 변경: '{state.current_effect}' -> '{effect}' (요청자: {interaction.user.display_name})")
        
        # 노래 재생 중에 효과를 변경하면 즉시 적용
        if state.current_song and state.voice_client and interaction.user.voice and interaction.user.voice.channel == state.voice_client.channel:
            if state.current_effect == effect: return await interaction.response.defer() # 같은 효과면 무시
            
            # 현재 재생 위치를 기억한 후, 효과를 적용하여 노래를 처음부터 다시 재생
            state.seek_time = state.get_current_playback_time()
            state.current_effect = effect
            state.queue.appendleft(state.current_song)
            state.voice_client.stop()
            await interaction.response.send_message(f"🎧 효과를 **{effect.capitalize()}**(으)로 즉시 변경합니다.", ephemeral=True, delete_after=5)
        # 노래가 없을 때 효과를 변경하면 다음 곡부터 적용
        else:
            state.current_effect = effect
            await state.schedule_ui_update()
            await interaction.response.send_message(f"🎧 다음 곡부터 **'{effect.capitalize()}'** 효과가 적용됩니다.", ephemeral=True)

async def setup(bot: commands.Bot):
    """봇에 이 Cog를 추가하기 위한 필수 함수입니다."""
    if MUSIC_CHANNEL_ID == 0:
        logger.error("환경변수에 MUSIC_CHANNEL_ID가 설정되지 않았습니다! music_agent를 로드하지 않습니다.")
        return
    await bot.add_cog(MusicAgentCog(bot))
