from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from cogs.application_commands import CommandsCog
from cogs.birthday.birthday_core import BirthdayCoreCog
from cogs.leveling.leveling_core import LevelingCog
from cogs.music.music_agent import MusicAgentCog
from main_bot import MyBot


COMMAND_CONTRACT = {
    "요약": ("최근 대화를 요약합니다.", [("hours", "number", False, 6.0)]),
    "재생": (
        "유튜브 링크나 검색어로 노래를 재생하고, 봇을 음성 채널로 자동 초대합니다.",
        [("검색어", "string", True, None)],
    ),
    "시청": (
        "외부 웹 브라우저에서 유튜브를 동시에 볼 수 있는 실시간 시청 방을 개설합니다.",
        [],
    ),
    "내정보": (
        "나의 현재 레벨과 경험치 진행도를 확인합니다.",
        [("user", "user", False, None)],
    ),
    "랭킹": (
        "서버 내 경험치 랭킹 TOP 10을 확인합니다.",
        [("ephemeral", "boolean", False, False)],
    ),
    "생일등록": (
        "[어드민 전용] 멤버의 생일을 등록합니다.",
        [
            ("user", "user", True, None),
            ("month", "integer", True, None),
            ("day", "integer", True, None),
        ],
    ),
    "생일삭제": (
        "[어드민 전용] 멤버의 생일 정보를 삭제합니다.",
        [("user", "user", True, None)],
    ),
    "생일목록": (
        "서버에 등록된 생일 목록을 확인합니다.",
        [("ephemeral", "boolean", False, False)],
    ),
}


def _command_objects() -> list[discord.app_commands.Command]:
    return [
        CommandsCog.summary_command,
        CommandsCog.play,
        CommandsCog.watch_command,
        LevelingCog.profile,
        LevelingCog.leaderboard,
        BirthdayCoreCog.register_birthday,
        BirthdayCoreCog.delete_birthday,
        BirthdayCoreCog.list_birthdays,
    ]


def _interaction(*, user_id: int = 10, guild_id: int = 20) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.display_name = "테스터"
    interaction.user.display_avatar.url = "https://example.invalid/avatar.png"
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id
    interaction.guild.name = "테스트 서버"
    interaction.guild_id = guild_id
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.followup.send = AsyncMock()
    return interaction


def test_f003_fr003_preserve_eight_slash_command_signatures() -> None:
    """Feature F003/F008/F012/F031-F035/F037; FR-003; PRESERVE."""
    actual = {}
    for command in _command_objects():
        params = []
        for parameter in command.parameters:
            default = None if parameter.required else parameter.default
            params.append(
                (parameter.name, parameter.type.name, parameter.required, default)
            )
        actual[command.name] = (command.description, params)

    assert actual == COMMAND_CONTRACT


def test_f044_fr007_preserve_mention_only_default_help_contract() -> None:
    """Feature F044; FR-007/FR-010; PRESERVE."""
    bot = MyBot(
        command_prefix=commands.when_mentioned,
        intents=discord.Intents.none(),
    )

    assert bot.command_prefix is commands.when_mentioned
    assert bot.get_command("help") is not None
    assert bot.help_command is not None
    assert bot.help_command.dm_help is False
    assert bot.help_command.verify_checks is True


@pytest.mark.asyncio
async def test_f008_fr003_fr010_preserve_summary_publicness_and_unready_error() -> None:
    """Feature F008; FR-003/FR-010/FR-027; PRESERVE."""
    summary = SimpleNamespace(execute_summary=AsyncMock())
    bot = MagicMock()
    bot.get_cog.return_value = summary
    cog = CommandsCog(bot)
    interaction = _interaction()

    await CommandsCog.summary_command.callback(cog, interaction, hours=3.0)

    interaction.response.defer.assert_awaited_once_with(
        thinking=True,
        ephemeral=False,
    )
    summary.execute_summary.assert_awaited_once_with(interaction, 3.0)

    bot.get_cog.return_value = None
    unavailable = _interaction()
    await CommandsCog.summary_command.callback(cog, unavailable, hours=6.0)
    unavailable.response.send_message.assert_awaited_once_with(
        "요약 기능이 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_f012_fr003_fr010_preserve_play_is_private_and_unready_error() -> None:
    """Feature F012; FR-003/FR-010/FR-012; PRESERVE."""
    interaction = _interaction()
    interaction.channel_id = 123
    interaction.channel = MagicMock()
    service = SimpleNamespace(
        bot=MagicMock(),
        _process_play_request=AsyncMock(),
    )
    service.bot.get_channel.return_value = MagicMock(mention="#music")

    with patch("cogs.music.music_agent.MUSIC_CHANNEL_ID", 123):
        await MusicAgentCog.handle_play(service, interaction, "검색어")

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    service._process_play_request.assert_awaited_once()

    bot = MagicMock()
    bot.get_cog.return_value = None
    unavailable = _interaction()
    await CommandsCog.play.callback(CommandsCog(bot), unavailable, 검색어="검색어")
    unavailable.response.send_message.assert_awaited_once_with(
        "노래 기능이 아직 준비되지 않았습니다.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_f031_f032_fr033_preserve_profile_and_ranking_publicness() -> None:
    """Features F031/F032; FR-003/FR-010/FR-033; PRESERVE."""
    cog = LevelingCog(MagicMock())
    profile_interaction = _interaction()
    with patch(
        "cogs.leveling.leveling_core.get_user_data",
        new=AsyncMock(return_value={"xp": 0, "level": 1, "total_vc_seconds": 0}),
    ):
        await LevelingCog.profile.callback(cog, profile_interaction, user=None)
    profile_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert "embed" in profile_interaction.followup.send.call_args.kwargs

    with patch(
        "cogs.leveling.leveling_core.get_top_users",
        new=AsyncMock(return_value=[]),
    ):
        public = _interaction()
        await LevelingCog.leaderboard.callback(cog, public, ephemeral=False)
        public.response.defer.assert_awaited_once_with(ephemeral=False)

        private = _interaction()
        await LevelingCog.leaderboard.callback(cog, private, ephemeral=True)
        private.response.defer.assert_awaited_once_with(ephemeral=True)


@pytest.mark.asyncio
async def test_f033_f034_fr005_fr010_preserve_birthday_master_error_contract() -> None:
    """Features F033/F034; FR-005/FR-010/FR-034; PRESERVE."""
    with patch("cogs.birthday.birthday_core.SUMMARY_CHANNEL_ID", 0), patch(
        "cogs.birthday.birthday_core.MASTER_USER_ID",
        42,
    ):
        cog = BirthdayCoreCog(MagicMock())
        user = MagicMock(spec=discord.Member)
        user.id = 99
        user.display_name = "친구"

        denied = _interaction(user_id=7)
        await BirthdayCoreCog.register_birthday.callback(
            cog,
            denied,
            user=user,
            month=9,
            day=4,
        )
        denied.response.send_message.assert_awaited_once_with(
            "이 명령어를 사용할 권한이 없습니다.",
            ephemeral=True,
        )

        allowed = _interaction(user_id=42)
        with patch(
            "cogs.birthday.birthday_core.add_birthday",
            new=AsyncMock(),
        ) as add_birthday:
            await BirthdayCoreCog.register_birthday.callback(
                cog,
                allowed,
                user=user,
                month=9,
                day=4,
            )
        add_birthday.assert_awaited_once_with(99, 20, 9, 4)
        allowed.response.send_message.assert_awaited_once_with(
            "✅ 친구 님의 생일을 9월 4일로 등록했습니다.",
            ephemeral=True,
        )


@pytest.mark.asyncio
async def test_f035_fr003_fr010_fr036_preserve_birthday_list_publicness() -> None:
    """Feature F035; FR-003/FR-010/FR-036; PRESERVE."""
    with patch("cogs.birthday.birthday_core.SUMMARY_CHANNEL_ID", 0):
        cog = BirthdayCoreCog(MagicMock())

    empty = _interaction()
    with patch(
        "cogs.birthday.birthday_core.get_all_birthdays",
        new=AsyncMock(return_value=[]),
    ):
        await BirthdayCoreCog.list_birthdays.callback(cog, empty, ephemeral=False)
    empty.response.send_message.assert_awaited_once_with(
        "현재 등록된 생일 정보가 없습니다.",
        ephemeral=True,
    )

    populated = _interaction()
    member = MagicMock(spec=discord.Member)
    member.display_name = "친구"
    populated.guild.get_member.return_value = member
    with patch(
        "cogs.birthday.birthday_core.get_all_birthdays",
        new=AsyncMock(return_value=[{"user_id": 99, "month": 9, "day": 4}]),
    ):
        await BirthdayCoreCog.list_birthdays.callback(
            cog,
            populated,
            ephemeral=False,
        )
    assert populated.response.send_message.call_args.kwargs["ephemeral"] is False


@pytest.mark.asyncio
async def test_f034_fr005_fr010_fr034_preserve_birthday_delete_result_contract() -> None:
    """Feature F034; FR-005/FR-010/FR-034; PRESERVE."""
    with patch("cogs.birthday.birthday_core.SUMMARY_CHANNEL_ID", 0), patch(
        "cogs.birthday.birthday_core.MASTER_USER_ID",
        42,
    ):
        cog = BirthdayCoreCog(MagicMock())
        user = MagicMock(spec=discord.Member)
        user.id = 99
        user.display_name = "친구"

        missing = _interaction(user_id=42)
        with patch(
            "cogs.birthday.birthday_core.remove_birthday",
            new=AsyncMock(return_value=0),
        ):
            await BirthdayCoreCog.delete_birthday.callback(cog, missing, user=user)
        missing.response.send_message.assert_awaited_once_with(
            "❌ 친구 님의 등록된 생일 정보가 없습니다.",
            ephemeral=True,
        )

        deleted = _interaction(user_id=42)
        with patch(
            "cogs.birthday.birthday_core.remove_birthday",
            new=AsyncMock(return_value=1),
        ):
            await BirthdayCoreCog.delete_birthday.callback(cog, deleted, user=user)
        deleted.response.send_message.assert_awaited_once_with(
            "✅ 친구 님의 생일 정보를 삭제했습니다.",
            ephemeral=True,
        )


@pytest.mark.asyncio
async def test_f003_fr004_fr010_correct_command_error_uses_one_private_responder() -> None:
    """Feature F003; FR-004/FR-010; CORRECT boundary already met by router."""
    bot = MagicMock()
    bot.log = MagicMock()
    cog = CommandsCog(bot)
    error = discord.app_commands.AppCommandError("failure")

    before_ack = _interaction()
    before_ack.command = MagicMock(name="요약")
    await cog.cog_app_command_error(before_ack, error)
    before_ack.response.send_message.assert_awaited_once_with(
        "명령어 처리 중 오류가 발생했습니다. 관리자에게 문의해주세요.",
        ephemeral=True,
    )
    before_ack.followup.send.assert_not_awaited()

    after_ack = _interaction()
    after_ack.command = MagicMock(name="요약")
    after_ack.response.is_done.return_value = True
    await cog.cog_app_command_error(after_ack, error)
    after_ack.followup.send.assert_awaited_once_with(
        "명령어 처리 중 오류가 발생했습니다. 관리자에게 문의해주세요.",
        ephemeral=True,
    )
    after_ack.response.send_message.assert_not_awaited()
