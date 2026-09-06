import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.birthday.birthday_core import BirthdayCoreCog
from cogs.leveling.leveling_core import LevelingCog
from discordbot.engagement.adapters.discord_runtime import VoiceGateway
from discordbot.engagement.adapters.discord_ui import DiscordBirthdayDelivery, EngagementCog
from discordbot.platform.errors import ConflictError, DatabaseUnavailableError


def interaction(user_id=10, guild_id=100):
    item = MagicMock(spec=discord.Interaction)
    item.user.id = user_id
    item.user.display_name = "테스터"
    item.user.display_avatar.url = "https://example.invalid/avatar.png"
    item.guild.id = guild_id
    item.guild.name = "테스트 서버"
    item.guild_id = guild_id
    item.response.is_done.return_value = False
    async def ack(*args, **kwargs):
        item.response.is_done.return_value = True
    item.response.defer = AsyncMock(side_effect=ack)
    item.response.send_message = AsyncMock(side_effect=ack)
    item.followup.send = AsyncMock()
    return item


def member(user_id=11):
    item = MagicMock(spec=discord.Member)
    item.id = user_id
    item.bot = False
    item.display_name = "친구"
    item.display_avatar.url = "https://example.invalid/friend.png"
    return item


def test_five_command_signatures_match_actual_v1(service):
    cog = EngagementCog(service)
    old = [LevelingCog.profile, LevelingCog.leaderboard, BirthdayCoreCog.register_birthday,
           BirthdayCoreCog.delete_birthday, BirthdayCoreCog.list_birthdays]
    expected = {c.name: (c.description, [(p.name, p.type.name, p.required, p.default) for p in c.parameters]) for c in old}
    actual = {c.name: (c.description, [(p.name, p.type.name, p.required, p.default) for p in c.parameters]) for c in cog.get_app_commands()}
    assert actual == expected


@pytest.mark.asyncio
async def test_profile_private_master_other_stealth_self_missing_and_dm(service):
    cog = EngagementCog(service)
    await service.repository.add_progress(100, 10, 7, 119, service.request())
    await service.repository.add_progress(100, 11, 100, 0, service.request())
    request = interaction()
    await cog.profile.callback(cog, request, member())
    request.response.defer.assert_awaited_once_with(ephemeral=True)
    embed = request.followup.send.call_args.kwargs["embed"]
    assert embed.title == "👤 테스터님의 정보"
    assert {f.name: f.value for f in embed.fields}["총 누적 경험치"] == "**12 XP**"
    admin = interaction(42)
    await cog.profile.callback(cog, admin, member())
    assert admin.followup.send.call_args.kwargs["embed"].title == "👤 친구님의 정보"
    missing = interaction(12)
    await cog.profile.callback(cog, missing, None)
    assert missing.followup.send.call_args.kwargs["embed"].fields[1].value == "**0 XP**"
    other_guild = interaction(10, 200)
    await cog.profile.callback(cog, other_guild, None)
    assert other_guild.followup.send.call_args.kwargs["embed"].fields[1].value == "**0 XP**"
    dm = interaction()
    dm.guild = None
    await cog.profile.callback(cog, dm, None)
    dm.followup.send.assert_awaited_once_with("이 명령어는 서버 내에서만 사용할 수 있습니다.", ephemeral=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("private", [False, True])
async def test_ranking_visibility_values_and_empty(service, private):
    cog = EngagementCog(service)
    item = interaction()
    await cog.leaderboard.callback(cog, item, private)
    item.response.defer.assert_awaited_once_with(ephemeral=private)
    assert item.followup.send.call_args.kwargs["embed"].description == "이 서버에 경험치가 기록된 유저가 없습니다."
    await service.repository.add_progress(100, 10, 7, 119, service.request())
    populated = interaction()
    populated.guild.get_member.return_value = member(10)
    await cog.leaderboard.callback(cog, populated, private)
    assert "(12 XP)" in populated.followup.send.call_args.kwargs["embed"].description


@pytest.mark.asyncio
async def test_birthday_denial_invalid_success_delete_and_empty_visibility(service):
    cog = EngagementCog(service)
    target = member()
    denied = interaction()
    await cog.register_birthday.callback(cog, denied, target, 9, 4)
    denied.response.send_message.assert_awaited_once_with("이 명령어를 사용할 권한이 없습니다.", ephemeral=True)
    invalid = interaction(42)
    await cog.register_birthday.callback(cog, invalid, target, 2, 31)
    invalid.response.send_message.assert_awaited_once_with("올바른 날짜를 입력해주세요.", ephemeral=True)
    good = interaction(42)
    await cog.register_birthday.callback(cog, good, target, 2, 29)
    good.followup.send.assert_awaited_once_with("✅ 친구 님의 생일을 2월 29일로 등록했습니다.", ephemeral=True)
    listed = interaction()
    listed.guild.get_member.return_value = target
    await cog.list_birthdays.callback(cog, listed, False)
    assert listed.response.send_message.call_args.kwargs["ephemeral"] is False
    assert "2월 29일" in listed.response.send_message.call_args.kwargs["embed"].description
    deleted = interaction(42)
    await cog.delete_birthday.callback(cog, deleted, target)
    deleted.followup.send.assert_awaited_once_with("✅ 친구 님의 생일 정보를 삭제했습니다.", ephemeral=True)
    empty = interaction()
    await cog.list_birthdays.callback(cog, empty, False)
    empty.response.send_message.assert_awaited_once_with("현재 등록된 생일 정보가 없습니다.", ephemeral=True)
    missing = interaction(42)
    await cog.delete_birthday.callback(cog, missing, member(999))
    missing.followup.send.assert_awaited_once_with("❌ 친구 님의 등록된 생일 정보가 없습니다.", ephemeral=True)


@pytest.mark.asyncio
async def test_one_private_error_responder_before_and_after_ack(service, monkeypatch):
    cog = EngagementCog(service)
    monkeypatch.setattr(service, "profile", AsyncMock(side_effect=DatabaseUnavailableError("private diagnostic")))
    after = interaction()
    await cog.profile.callback(cog, after, None)
    after.response.send_message.assert_not_awaited()
    after.followup.send.assert_awaited_once()
    assert after.followup.send.call_args.kwargs["ephemeral"] is True
    monkeypatch.setattr(service, "birthdays", AsyncMock(side_effect=DatabaseUnavailableError("private diagnostic")))
    before = interaction()
    await cog.list_birthdays.callback(cog, before, False)
    before.response.send_message.assert_awaited_once()
    before.followup.send.assert_not_awaited()
    assert "diagnostic" not in before.response.send_message.call_args.args[0]


@pytest.mark.asyncio
async def test_large_birthday_list_respects_embed_limit_without_dropping_users(service, database):
    await database.write(service.request(), lambda conn: conn.executemany("INSERT INTO users(user_id,guild_id,birth_month,birth_day) VALUES (?,100,2,28)", [(i,) for i in range(1, 205)]))
    cog = EngagementCog(service)
    item = interaction()
    item.guild.get_member.side_effect = lambda uid: SimpleNamespace(display_name=f"friend-{uid}-" + "한" * 30)
    await cog.list_birthdays.callback(cog, item, True)
    embeds = [call.kwargs["embed"] for call in item.response.send_message.call_args_list + item.followup.send.call_args_list]
    assert all(len(embed.description) <= 4096 for embed in embeds)
    assert sum(embed.description.count("• **") for embed in embeds) == 204
    assert all(call.kwargs["ephemeral"] for call in item.followup.send.call_args_list)


@pytest.mark.asyncio
async def test_delivery_never_crosses_guild_channel(service):
    bot = MagicMock()
    channel = MagicMock(spec=discord.TextChannel)
    channel.guild.id = 200
    channel.send = AsyncMock()
    bot.get_channel.return_value = channel
    delivery = DiscordBirthdayDelivery(bot)
    with pytest.raises(ConflictError):
        await delivery.send(100, 1001, (10,))
    channel.send.assert_not_awaited()
    channel.guild.id = 100
    await delivery.send(100, 1001, (10,))
    assert channel.send.call_args.kwargs["embed"].description == "@everyone 오늘은 <@10> 님의 생일입니다!\n모두 축하해주세요! 🎂🎁"


@pytest.mark.asyncio
async def test_gateway_ready_resume_duplicate_and_each_mute_flag(service, clock):
    bot = MagicMock()
    bot.guilds = []
    gateway = VoiceGateway(bot, service)
    await gateway.receive(json.dumps({"op": 0, "t": "READY", "s": 1, "d": {"session_id": "synthetic-gateway-session"}}))
    stream = gateway.stream
    assert "synthetic-gateway-session" not in stream
    def packet(seq, channel, **flags):
        return json.dumps({"op": 0, "t": "VOICE_STATE_UPDATE", "s": seq, "d": {"guild_id": "100", "user_id": "10", "channel_id": channel, "member": {"user": {"id": "10", "bot": False}}, **flags}})
    await gateway.receive(packet(2, "1001"))
    clock.advance(61)
    seq = 3
    for flag in ("self_mute", "mute", "self_deaf", "deaf"):
        await gateway.receive(packet(seq, "1001", **{flag: True}))
        clock.advance(100)
        await gateway.receive(packet(seq + 1, "1001"))
        seq += 2
    leave = packet(seq, None)
    await gateway.receive(leave)
    await gateway.receive(json.dumps({"op": 0, "t": "RESUMED", "s": seq + 1, "d": {}}))
    await gateway.receive(leave)
    await gateway.ready()
    assert gateway.stream == stream
    assert (await service.profile(100, 10)).seconds == 61


@pytest.mark.asyncio
async def test_actual_composition_registers_only_engagement_and_closes_without_network(database, clock):
    from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
    from discordbot.composition.engagement import build_engagement
    from discordbot.engagement.ports.events import EngagementConfig
    config = PlatformConfig(service=ServiceKind.DISCORD_BOT, environment=Environment.TEST, release="engagement-test")
    runtime, feature = build_engagement(config, database.config, EngagementConfig(42, ((100, 1001),)), clock=clock)
    await runtime.start()
    try:
        assert {command.name for command in feature.bot.tree.get_commands()} == {"내정보", "랭킹", "생일등록", "생일삭제", "생일목록"}
        assert not feature.bot.is_ready()  # No login or network connection.
        assert not feature.supervisor.snapshot().active
        await feature.ready()
        assert len(feature.supervisor.snapshot().active) == 1
    finally:
        report = await runtime.shutdown()
    assert report.resource_errors == ()
    assert feature.bot.is_closed()
    await feature.ready()  # A late SDK ready callback cannot resurrect the stopped scheduler.
    assert not feature.supervisor.snapshot().active


@pytest.mark.asyncio
async def test_repeated_ready_seeds_live_nonbot_members_once_in_each_guild(service, clock):
    bot = MagicMock()
    bot.guilds = []
    for guild_id in (100, 200):
        human = SimpleNamespace(id=10, bot=False, voice=SimpleNamespace(self_mute=False, mute=False, self_deaf=False, deaf=False))
        robot = SimpleNamespace(id=11, bot=True, voice=None)
        bot.guilds.append(SimpleNamespace(id=guild_id, voice_channels=[SimpleNamespace(id=guild_id+1, members=[human, robot])]))
    gateway = VoiceGateway(bot, service)
    await gateway.ready()
    clock.advance(61)
    await gateway.ready()
    for guild_id in (100, 200):
        await service.voice(guild_id, 10, gateway.stream, 1, None, False)
        assert (await service.profile(guild_id, 10)).seconds == 61
        assert await service.repository.get_member(guild_id, 11, service.request()) is None


@pytest.mark.asyncio
async def test_phase3_database_requires_explicit_copy_expansion_before_feature_start(tmp_path, clock):
    import sqlite3
    from contextlib import closing
    from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
    from discordbot.composition.engagement import build_engagement
    from discordbot.engagement.ports.events import EngagementConfig
    from discordbot.platform.errors import StartupError
    from discordbot.storage.adapters.migrations import MIGRATIONS, apply_pending
    from discordbot.storage.adapters.schema import create_legacy_schema
    from discordbot.storage.ports.contracts import DatabaseConfig
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        create_legacy_schema(conn)
        apply_pending(conn, lambda: None, MIGRATIONS[:2])
    before = path.read_bytes()
    config = PlatformConfig(service=ServiceKind.DISCORD_BOT, environment=Environment.TEST, release="old-schema-test")
    runtime, feature = build_engagement(config, DatabaseConfig(path), EngagementConfig(42), clock=clock)
    with pytest.raises(StartupError):
        await runtime.start()
    assert feature.bot.is_closed()
    assert not feature.supervisor.snapshot().active
    assert path.read_bytes() == before
    await runtime.shutdown()
