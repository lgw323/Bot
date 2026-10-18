import logging
from typing import Any, Mapping

import discord
from discord.ext import commands

from .music_core import MusicState
from .music_utils import LoopMode, Song


logger: logging.Logger = logging.getLogger(__name__)


class MusicSessionRestorer:
    """Apply one saved session to Discord and the active music state."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def restore(
        self,
        guild: discord.Guild,
        state: MusicState,
        data: Mapping[str, Any],
    ) -> None:
        logger.info("[%s] 이전 음악 세션 복원 시작...", guild.name)

        state.volume = data.get("volume", 1.0)
        state.loop_mode = LoopMode[data.get("loop_mode", "NONE")]
        state.auto_play_enabled = data.get("auto_play_enabled", False)
        state.seek_time = data.get("elapsed_seconds", 0)

        text_channel_id = data.get("text_channel_id")
        if text_channel_id:
            state.text_channel = self.bot.get_channel(text_channel_id)

        saved_queue = data.get("queue", [])
        for item in saved_queue:
            requester = guild.get_member(item.get("requester_id")) or guild.me
            state.queue.append(Song(item, requester))

        saved_current = data.get("current_song")
        if saved_current:
            requester = (
                guild.get_member(saved_current.get("requester_id"))
                or guild.me
            )
            state.queue.appendleft(Song(saved_current, requester))

        voice_channel_id = data.get("voice_channel_id")
        if voice_channel_id:
            voice_channel = self.bot.get_channel(voice_channel_id)
            if voice_channel and isinstance(
                voice_channel,
                discord.VoiceChannel,
            ):
                try:
                    state.voice_client = await voice_channel.connect(
                        timeout=20.0,
                        self_deaf=True,
                    )
                    logger.info(
                        "[%s] 음성 채널 자동 재연결 성공. (채널: %s)",
                        guild.name,
                        voice_channel.name,
                    )
                except Exception as e:
                    logger.error(
                        "[%s] 음성 채널 자동 재연결 실패: %s",
                        guild.name,
                        e,
                    )

        if state.voice_client and (saved_current or saved_queue):
            state.play_next_song.set()
