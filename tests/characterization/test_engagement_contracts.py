import datetime as stdlib_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import database_manager
from cogs.birthday import birthday_core
from cogs.birthday.birthday_core import BirthdayCoreCog
from cogs.leveling import leveling_core
from cogs.leveling.leveling_core import LevelingCog, calculate_jamo_length


def _voice_state(channel: object | None, *, muted: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        channel=channel,
        self_mute=muted,
        mute=False,
        self_deaf=False,
        deaf=False,
    )


def _member() -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = 101
    member.bot = False
    member.guild.id = 202
    member.mention = "<@101>"
    return member


def test_f029_fr031_preserve_text_xp_character_table() -> None:
    """Feature F029; FR-031; PRESERVE."""
    assert calculate_jamo_length("") == 0
    assert calculate_jamo_length("   \n\t") == 0
    assert calculate_jamo_length("가") == 2
    assert calculate_jamo_length("각") == 3
    assert calculate_jamo_length("힣") == 3
    assert calculate_jamo_length("abc 123") == 6
    assert calculate_jamo_length("🙂!") == 2
    assert calculate_jamo_length("안녕 abc!") == 10


@pytest.mark.asyncio
async def test_f030_fr032_preserve_voice_xp_fake_clock_and_completed_minutes() -> None:
    """Feature F030; FR-032; PRESERVE/CORRECT fake-clock contract."""
    cog = LevelingCog(MagicMock())
    member = _member()
    channel = object()
    cog.voice_sessions[member.id] = {
        "time": 1_000.0,
        "guild_id": member.guild.id,
        "is_muted_or_deafened": False,
        "last_state_change": 1_000.0,
        "valid_duration": 0.0,
    }

    with patch.object(leveling_core.time, "time", return_value=1_125.9), patch(
        "cogs.leveling.leveling_core.get_user_data",
        new=AsyncMock(return_value={"level": 1, "xp": 0, "total_vc_seconds": 0}),
    ), patch(
        "cogs.leveling.leveling_core.update_user_xp",
        new=AsyncMock(),
    ) as update_xp:
        await cog.on_voice_state_update(
            member,
            _voice_state(channel),
            _voice_state(None),
        )

    update_xp.assert_awaited_once_with(
        member.id,
        member.guild.id,
        xp_added=0,
        vc_sec_added=125,
        new_level=None,
    )
    assert member.id not in cog.voice_sessions


@pytest.mark.asyncio
async def test_f030_fr032_preserve_voice_move_keeps_one_session() -> None:
    """Feature F030; FR-032; PRESERVE voice-move meaning."""
    cog = LevelingCog(MagicMock())
    member = _member()
    session = {
        "time": 1_000.0,
        "guild_id": member.guild.id,
        "is_muted_or_deafened": False,
        "last_state_change": 1_000.0,
        "valid_duration": 15.0,
    }
    cog.voice_sessions[member.id] = session

    with patch(
        "cogs.leveling.leveling_core.update_user_xp",
        new=AsyncMock(),
    ) as update_xp:
        await cog.on_voice_state_update(
            member,
            _voice_state(object()),
            _voice_state(object()),
        )

    assert cog.voice_sessions[member.id] is session
    update_xp.assert_not_awaited()


@pytest.mark.asyncio
async def test_f031_fr032_fr033_preserve_profile_completed_minute_formula() -> None:
    """Feature F031; FR-032/FR-033; PRESERVE."""
    cog = LevelingCog(MagicMock())
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild.id = 202
    interaction.user.id = 101
    interaction.user.display_name = "테스터"
    interaction.user.display_avatar.url = "https://example.invalid/avatar.png"
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.response.is_done.return_value = True

    with patch(
        "cogs.leveling.leveling_core.get_user_data",
        new=AsyncMock(return_value={"level": 1, "xp": 7, "total_vc_seconds": 119}),
    ):
        await LevelingCog.profile.callback(cog, interaction, user=None)

    embed = interaction.followup.send.call_args.kwargs["embed"]
    fields = {field.name: field.value for field in embed.fields}
    assert fields["총 누적 경험치"] == "**12 XP**"
    assert "🎙️ 음성: 5 XP" in fields["경험치 상세"]


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: V1 ranking uses fractional voice minutes",
)
@pytest.mark.asyncio
async def test_f032_fr032_fr033_correct_ranking_matches_profile_completed_minutes() -> None:
    """Feature F032; FR-032/FR-033; CORRECT."""
    guild_id = 98_765
    user_id = 54_321
    await database_manager.update_user_xp(
        user_id,
        guild_id,
        xp_added=0,
        vc_sec_added=119,
    )

    rows = await database_manager.get_top_users(guild_id)

    assert rows[0]["total_xp"] == 5


class _LeapDayClock(stdlib_datetime.datetime):
    @classmethod
    def now(cls, tz: stdlib_datetime.tzinfo | None = None) -> "_LeapDayClock":
        return cls(2028, 2, 29, 9, 0, tzinfo=tz)


class _NonLeapFeb28Clock(stdlib_datetime.datetime):
    @classmethod
    def now(cls, tz: stdlib_datetime.tzinfo | None = None) -> "_NonLeapFeb28Clock":
        return cls(2027, 2, 28, 9, 0, tzinfo=tz)


def _birthday_cog() -> tuple[BirthdayCoreCog, MagicMock, MagicMock]:
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    guild = MagicMock(spec=discord.Guild)
    guild.id = 202
    guild.name = "테스트 서버"
    member = _member()
    guild.get_member.return_value = member
    bot.guilds = [guild]
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    bot.get_channel.return_value = channel
    with patch.object(birthday_core, "SUMMARY_CHANNEL_ID", 0):
        cog = BirthdayCoreCog(bot)
    return cog, guild, channel


@pytest.mark.asyncio
async def test_f036_fr037_preserve_kst_nine_oclock_fake_clock() -> None:
    """Feature F036; FR-037; PRESERVE fake-clock contract."""
    cog, guild, channel = _birthday_cog()
    assert cog.target_time.hour == 9
    assert cog.target_time.minute == 0
    assert cog.target_time.utcoffset() == stdlib_datetime.timedelta(hours=9)

    with patch.object(birthday_core, "SUMMARY_CHANNEL_ID", 303), patch.object(
        birthday_core.datetime,
        "datetime",
        _LeapDayClock,
    ), patch(
        "cogs.birthday.birthday_core.get_birthdays_today",
        new=AsyncMock(return_value=[101]),
    ) as birthdays_today:
        await BirthdayCoreCog.birthday_loop.coro(cog)

    birthdays_today.assert_awaited_once_with(guild.id, 2, 29)
    channel.send.assert_awaited_once()
    embed = channel.send.call_args.kwargs["embed"]
    assert "<@101>" in embed.description


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: V1 accepts calendar-impossible dates",
)
@pytest.mark.asyncio
async def test_f033_fr035_correct_rejects_invalid_calendar_date() -> None:
    """Feature F033; FR-035; CORRECT."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.id = 42
    interaction.guild_id = 202
    interaction.response.send_message = AsyncMock()
    user = _member()
    with patch.object(birthday_core, "SUMMARY_CHANNEL_ID", 0), patch.object(
        birthday_core,
        "MASTER_USER_ID",
        42,
    ):
        cog = BirthdayCoreCog(MagicMock())
        with patch(
            "cogs.birthday.birthday_core.add_birthday",
            new=AsyncMock(),
        ) as add_birthday:
            await BirthdayCoreCog.register_birthday.callback(
                cog,
                interaction,
                user=user,
                month=2,
                day=30,
            )

    add_birthday.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(
        "올바른 날짜를 입력해주세요.",
        ephemeral=True,
    )


@pytest.mark.xfail(
    strict=True,
    reason="CORRECT contract: non-leap Feb 28 must also query Feb 29 birthdays",
)
@pytest.mark.asyncio
async def test_f036_fr035_fr037_correct_non_leap_feb29_fallback_fake_clock() -> None:
    """Feature F036; FR-035/FR-037; CORRECT."""
    cog, guild, _channel = _birthday_cog()
    with patch.object(birthday_core, "SUMMARY_CHANNEL_ID", 303), patch.object(
        birthday_core.datetime,
        "datetime",
        _NonLeapFeb28Clock,
    ), patch(
        "cogs.birthday.birthday_core.get_birthdays_today",
        new=AsyncMock(return_value=[]),
    ) as birthdays_today:
        await BirthdayCoreCog.birthday_loop.coro(cog)

    birthdays_today.assert_awaited_once_with(guild.id, 2, 29)
