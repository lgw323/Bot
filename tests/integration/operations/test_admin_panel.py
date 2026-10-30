import asyncio
from datetime import datetime, timezone
import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.discord_admin import OperationsPanel, OperationalStatus, PanelStore, SystemdManualConsumer, status_embed
from discordbot.operations.adapters.filesystem import atomic_json, read_json
from discordbot.operations.adapters.manual import RequestInbox
from discordbot.operations.application.manual import ManualOperations
from discordbot.platform.errors import ValidationError
from discordbot.platform.executors import BoundedExecutor
from discordbot.platform.tasks import TaskSupervisor


def interaction(user=1, channel=42, message=444):
    done = [False]
    async def mark(*args, **kwargs): done[0] = True
    return SimpleNamespace(user=SimpleNamespace(id=user), channel_id=channel,
        message=SimpleNamespace(id=message, edit=AsyncMock()),
        response=SimpleNamespace(is_done=lambda: done[0], defer=AsyncMock(side_effect=mark), send_message=AsyncMock(side_effect=mark)),
        followup=SimpleNamespace(send=AsyncMock()))


class Status:
    def __init__(self):
        self.value = dict(release="r-test", ready=True, consumer_enabled=True,
                          request_operation=None, request_result=None, inbox_revision="a"*64,
                          outcome=None, pending=False, revision="b"*64)
    async def snapshot(self): return dict(self.value)


@pytest_asyncio.fixture
async def panel(tmp_path):
    ticks = [10.]
    clock = SimpleNamespace(monotonic=lambda: ticks[0], now=lambda: datetime.now(timezone.utc))
    supervisor = TaskSupervisor(capacity=8, history_capacity=32, clock=clock)
    executor = BoundedExecutor(workers=1, queue_capacity=8, name="panel-test")
    message = SimpleNamespace(id=444, edit=AsyncMock())
    channel = SimpleNamespace(send=AsyncMock(return_value=message), get_partial_message=Mock(return_value=message))
    listeners, views = {}, []
    bot = SimpleNamespace(get_channel=lambda _: channel, fetch_channel=AsyncMock(return_value=channel),
        add_view=lambda v, **kw: views.append((v, kw)),
        add_listener=lambda fn, event: listeners.setdefault(event, fn),
        remove_listener=lambda fn, event: listeners.pop(event, None))
    inbox = SimpleNamespace(accept_current=AsyncMock(return_value="accepted"))
    status = Status()
    resource = OperationsPanel(bot, master=1, channel=42, state=tmp_path, inbox=inbox,
        status=status, clock=clock, supervisor=supervisor, executor=executor)
    await resource.start(); await resource.ready()
    yield SimpleNamespace(resource=resource, status=status, inbox=inbox, ticks=ticks,
                          views=views, channel=channel, bot=bot, executor=executor,
                          supervisor=supervisor, clock=clock, tmp_path=tmp_path, listeners=listeners)
    await resource.stop()
    await supervisor.shutdown(grace_seconds=1)
    await executor.close(grace_seconds=2)


@pytest.mark.asyncio
async def test_persistent_panel_restores_message_handlers_without_duplicate_send(panel):
    first = panel.resource
    assert first.view.is_persistent()
    assert [x.custom_id for x in first.view.children] == ["ops:v1:refresh", "ops:v1:update", "ops:v1:restart"]
    await first.stop()
    second = OperationsPanel(panel.bot, master=1, channel=42, state=panel.tmp_path, inbox=panel.inbox,
        status=panel.status, clock=panel.clock, supervisor=panel.supervisor, executor=panel.executor)
    await second.start(); await second.ready()
    try:
        assert second.message_id == 444
        assert panel.views[-1][1] == {"message_id": 444}
        assert panel.channel.send.await_count == 1
        i = interaction(); await second.view.children[0].callback(i)
        i.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        i.message.edit.assert_awaited_once()
        i.followup.send.assert_awaited_once()
    finally: await second.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("user,channel,message", [(2,42,444), (True,42,444), (1,99,444), (1,42,999)])
async def test_every_main_callback_authorizes_user_channel_and_bound_message(panel, user, channel, message):
    for action in ["refresh", "update", "restart"]:
        i = interaction(user, channel, message)
        await panel.resource.interact(i, action)
        i.response.send_message.assert_awaited_once()
        assert not i.response.defer.called
    panel.inbox.accept_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_and_restart_require_explicit_confirmation(panel):
    for op in ["update", "restart"]:
        i = interaction(); await panel.resource.interact(i, op)
        panel.inbox.accept_current.assert_not_awaited()
        nonce = next(iter(panel.resource.confirmations))
        confirm = interaction(message=777)
        view = panel.resource.confirm_views[nonce]
        await view.children[0].callback(confirm)
        panel.inbox.accept_current.assert_awaited_once_with(op, nonce, "a"*64)
        assert "아직 실행 완료가 아닙니다" in confirm.followup.send.call_args.args[0]
        panel.inbox.accept_current.reset_mock()


@pytest.mark.asyncio
async def test_confirmation_rechecks_authorization_and_does_not_consume_on_attack(panel):
    await panel.resource.interact(interaction(), "restart")
    nonce = next(iter(panel.resource.confirmations))
    for i in [interaction(user=2,message=777), interaction(channel=99,message=777)]:
        await panel.resource.interact(i, "confirm", nonce)
        i.response.send_message.assert_awaited_once()
    assert nonce in panel.resource.confirmations
    panel.inbox.accept_current.assert_not_awaited()
    await panel.resource.interact(interaction(message=777), "confirm", nonce)
    panel.inbox.accept_current.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_confirmation_queues_once(panel):
    await panel.resource.interact(interaction(), "restart")
    nonce = next(iter(panel.resource.confirmations))
    await asyncio.gather(*(panel.resource.interact(interaction(message=777), "confirm", nonce) for _ in range(5)))
    panel.inbox.accept_current.assert_awaited_once()
    assert panel.resource.stale == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["timeout", "revision", "release", "consumer", "ready", "pending"])
async def test_stale_confirmation_refuses_every_changed_execution_gate(panel, change):
    await panel.resource.interact(interaction(), "update")
    nonce = next(iter(panel.resource.confirmations))
    if change == "timeout": panel.ticks[0] += 61
    elif change == "revision": panel.status.value["revision"] = "c"*64
    elif change == "release": panel.status.value["release"] = "r-new"
    elif change == "consumer": panel.status.value["consumer_enabled"] = False
    elif change == "ready": panel.status.value["ready"] = False
    else: panel.status.value["pending"] = True
    await panel.resource.interact(interaction(message=777), "confirm", nonce)
    panel.inbox.accept_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_new_prompt_and_resource_restart_invalidate_old_confirmation(panel):
    await panel.resource.interact(interaction(), "update")
    old = next(iter(panel.resource.confirmations))
    await panel.resource.interact(interaction(), "restart")
    new = next(iter(panel.resource.confirmations))
    assert old != new
    await panel.resource.interact(interaction(message=777), "confirm", old)
    await panel.resource.interact(interaction(message=777), "cancel", new)
    panel.inbox.accept_current.assert_not_awaited()
    assert not panel.resource.confirmations
    await panel.resource.interact(interaction(), "restart")
    await panel.resource.stop()
    assert not panel.resource.confirmations
    assert not panel.resource.confirm_views


@pytest.mark.asyncio
async def test_disabled_consumer_disables_controls_and_refuses_forged_click(panel):
    panel.status.value["consumer_enabled"] = False
    i = interaction(); await panel.resource.interact(i, "refresh")
    assert [x.disabled for x in panel.resource.view.children] == [False, True, True]
    await panel.resource.interact(interaction(), "update")
    assert not panel.resource.confirmations
    panel.inbox.accept_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_timeout_removes_confirmation_view(panel):
    await panel.resource.interact(interaction(), "restart")
    nonce = next(iter(panel.resource.confirmations))
    view = panel.resource.confirm_views[nonce]
    await view.on_timeout()
    assert nonce not in panel.resource.confirmations
    view.stop()


@pytest.mark.asyncio
async def test_status_failure_and_unknown_action_do_not_execute_or_leak(panel):
    panel.status.snapshot = AsyncMock(side_effect=OSError("private token secret"))
    i = interaction(); await panel.resource.interact(i, "refresh")
    assert "private" not in str(i.followup.send.call_args)
    await panel.resource.interact(interaction(), "shell-command")
    assert not panel.resource.confirmations
    panel.inbox.accept_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_cancels_only_owned_waiting_interaction(panel):
    entered = asyncio.Event()
    async def wait(): entered.set(); await asyncio.Future()
    panel.status.snapshot = wait
    task = asyncio.create_task(panel.resource.interact(interaction(), "refresh"))
    await entered.wait(); await panel.resource.stop()
    with pytest.raises(asyncio.CancelledError): await task
    assert not panel.resource.tasks
    panel.inbox.accept_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_unauthorized_hung_reply_is_bounded_and_never_queues(panel):
    i = interaction(user=2)
    async def hang(*args, **kwargs): await asyncio.Future()
    i.response.send_message.side_effect = hang
    await asyncio.wait_for(panel.resource.interact(i,"restart"),timeout=4)
    assert panel.resource.response_uncertain == 1
    i.response.send_message.assert_awaited_once()
    panel.inbox.accept_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_hung_initial_ack_is_bounded_without_new_reply_or_request(panel):
    i = interaction()
    async def hang(*args, **kwargs): await asyncio.Future()
    i.response.defer.side_effect = hang
    await asyncio.wait_for(panel.resource.interact(i,"restart"),timeout=3)
    assert panel.resource.response_uncertain == 1
    assert not panel.resource.confirmations
    i.response.defer.assert_awaited_once()
    i.followup.send.assert_not_awaited()
    panel.inbox.accept_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_cancels_waiting_initial_ack_without_admitting_request(panel):
    i = interaction(); entered = asyncio.Event()
    async def hang(*args, **kwargs): entered.set(); await asyncio.Future()
    i.response.defer.side_effect = hang
    task = asyncio.create_task(panel.resource.interact(i,"restart"))
    await entered.wait(); await panel.resource.stop()
    with pytest.raises(asyncio.CancelledError): await task
    assert not panel.resource.callbacks
    panel.inbox.accept_current.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["denied", "refresh"])
async def test_callback_burst_has_hard_admission_cap_and_owned_cleanup(panel, kind):
    started = []
    interactions = [interaction(user=2 if kind == "denied" else 1) for _ in range(100)]
    def blocking_reply(i):
        async def wait(*args, **kwargs):
            started.append(i)
            await asyncio.Future()
        return wait
    for i in interactions:
        if kind == "denied":
            i.response.send_message.side_effect = blocking_reply(i)
        else:
            i.response.defer.side_effect = blocking_reply(i)
    tasks = [asyncio.create_task(panel.resource.interact(i, "refresh")) for i in interactions]
    while len(started) < 32:
        await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(panel.resource.callbacks) == 32
    assert panel.resource.callback_overflow == 68
    assert panel.resource.gauges()["operations_panel_callback_depth"] == 32
    assert panel.resource.gauges()["operations_panel_callback_capacity"] == 32
    assert panel.resource.gauges()["operations_panel_callback_overflow"] == 68
    admitted = {id(i) for i in started}
    for i in interactions:
        if id(i) not in admitted:
            i.response.defer.assert_not_awaited()
            i.response.send_message.assert_not_awaited()
            i.followup.send.assert_not_awaited()
    panel.inbox.accept_current.assert_not_awaited()
    await panel.resource.stop()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert sum(isinstance(result, asyncio.CancelledError) for result in results) == 32
    assert not panel.resource.callbacks and not panel.resource.tasks
    assert panel.resource.gauges()["operations_panel_callback_depth"] == 0
    panel.inbox.accept_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_uncertain_accepted_reply_does_not_repeat_atomic_acceptance(panel):
    await panel.resource.interact(interaction(),"restart")
    nonce = next(iter(panel.resource.confirmations)); i = interaction(message=777)
    async def hang(*args, **kwargs): await asyncio.Future()
    i.followup.send.side_effect = hang
    await asyncio.wait_for(panel.resource.interact(i,"confirm",nonce),timeout=4)
    assert panel.resource.response_uncertain == 1
    assert not panel.resource.confirmations
    panel.inbox.accept_current.assert_awaited_once()
    i.followup.send.assert_awaited_once()
    await panel.resource.interact(interaction(message=777),"confirm",nonce)
    panel.inbox.accept_current.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_discord_persistent_registration_is_removed_on_stop(panel):
    import discord
    from discord.ext import commands
    bot = commands.Bot(command_prefix="!",intents=discord.Intents.none())
    resource = OperationsPanel(bot,master=1,channel=42,state=panel.tmp_path,inbox=panel.inbox,
        status=panel.status,clock=panel.clock,supervisor=panel.supervisor,executor=panel.executor)
    try:
        await resource.start()
        assert resource.view in bot.persistent_views
        await resource.stop()
        assert resource.view not in bot.persistent_views
    finally:
        await resource.stop(); await bot.close()


@pytest.mark.asyncio
async def test_confirmed_missing_message_is_replaced_exactly_once(panel):
    import discord
    old = read_json(panel.tmp_path/"operations-panel.json")
    missing = discord.NotFound(SimpleNamespace(status=404,reason="missing"),{"message":"Unknown Message","code":10008})
    partial = panel.channel.get_partial_message.return_value
    partial.edit.side_effect = missing
    panel.channel.send.return_value = SimpleNamespace(id=445)
    await panel.resource.ready()
    current = read_json(panel.tmp_path/"operations-panel.json")
    assert current["state"] == "published" and current["message"] == 445
    assert current["nonce"] != old["nonce"]
    assert panel.channel.send.await_count == 2
    partial.edit.side_effect = None
    await panel.resource.ready(); await panel.resource.ready()
    assert panel.channel.send.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["forbidden", "timeout", "other_404"])
async def test_no_panel_replacement_for_permission_unknown_or_other_missing_resource(panel,kind):
    import discord
    before = read_json(panel.tmp_path/"operations-panel.json")
    response = SimpleNamespace(status=403 if kind=="forbidden" else 404,reason="synthetic")
    error = (discord.Forbidden(response,{"message":"forbidden","code":50013}) if kind=="forbidden"
             else TimeoutError() if kind=="timeout" else discord.NotFound(response,{"message":"Unknown Channel","code":10003}))
    panel.channel.get_partial_message.return_value.edit.side_effect = error
    await panel.resource.ready()
    assert read_json(panel.tmp_path/"operations-panel.json") == before
    assert panel.channel.send.await_count == 1
    assert panel.resource.failures == 1


@pytest.mark.asyncio
async def test_missing_panel_recovery_does_not_overwrite_concurrent_marker(panel):
    import discord
    changed = {"version":1,"channel":42,"message":None,"nonce":"b"*24,"state":"publishing"}
    async def gone(**kwargs):
        atomic_json(panel.tmp_path/"operations-panel.json",changed)
        raise discord.NotFound(SimpleNamespace(status=404,reason="missing"),{"message":"Unknown Message","code":10008})
    panel.channel.get_partial_message.return_value.edit.side_effect = gone
    await panel.resource.ready()
    assert read_json(panel.tmp_path/"operations-panel.json") == changed
    assert panel.channel.send.await_count == 1
    assert panel.resource.message_id is None


@pytest.mark.asyncio
async def test_cancel_during_retained_accept_preserves_one_request_without_followup(panel,monkeypatch):
    (panel.tmp_path/"audit").mkdir()
    inbox = RequestInbox(panel.tmp_path,panel.tmp_path/"lock",panel.executor,Audit(panel.tmp_path/"audit"),"r-test")
    snapshot = await inbox.snapshot();panel.status.value["inbox_revision"] = snapshot["revision"]
    panel.resource.operations = ManualOperations(1,inbox)
    await panel.resource.interact(interaction(),"restart")
    nonce = next(iter(panel.resource.confirmations))
    entered,release = threading.Event(),threading.Event();original=inbox._accept
    def blocked(*args):
        entered.set();assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(inbox,"_accept",blocked)
    i=interaction(message=777);task=asyncio.create_task(panel.resource.interact(i,"confirm",nonce))
    while not entered.is_set():await asyncio.sleep(.001)
    stopping=asyncio.create_task(panel.resource.stop());await asyncio.sleep(.01);release.set()
    await stopping
    with pytest.raises(asyncio.CancelledError):await task
    i.followup.send.assert_not_awaited()
    row=read_json(panel.tmp_path/"manual-request.json")
    assert row["receipt"]==hashlib.sha256(nonce.encode()).hexdigest() and row["result"]=="pending"
    assert len(list((panel.tmp_path/"audit").iterdir()))==1


@pytest.mark.asyncio
async def test_cancel_during_retained_claim_never_starts_transport(panel,monkeypatch):
    state=panel.tmp_path/"new-panel";state.mkdir()
    resource=OperationsPanel(panel.bot,master=1,channel=42,state=state,inbox=panel.inbox,
        status=panel.status,clock=panel.clock,supervisor=panel.supervisor,executor=panel.executor)
    await resource.start()
    entered,release=threading.Event(),threading.Event();original=resource.store.claim
    def blocked():
        entered.set();assert release.wait(3)
        return original()
    monkeypatch.setattr(resource.store,"claim",blocked)
    task=asyncio.create_task(resource.ready())
    while not entered.is_set():await asyncio.sleep(.001)
    stopping=asyncio.create_task(resource.stop());await asyncio.sleep(.01);release.set()
    await stopping
    with pytest.raises(asyncio.CancelledError):await task
    assert panel.channel.send.await_count==1
    assert read_json(state/"operations-panel.json")["state"]=="publishing"


@pytest.mark.asyncio
async def test_uncertain_panel_publication_is_not_repeated_on_restart(panel):
    await panel.resource.stop()
    atomic_json(panel.tmp_path/"operations-panel.json", {"version":1,"channel":42,"message":None,"nonce":"a"*24,"state":"publishing"})
    resource = OperationsPanel(panel.bot, master=1, channel=42, state=panel.tmp_path, inbox=panel.inbox,
        status=panel.status, clock=panel.clock, supervisor=panel.supervisor, executor=panel.executor)
    await resource.start(); await resource.ready(); await resource.ready()
    try:
        assert resource.uncertain_publications == 2
        assert resource.message_id is None
        assert panel.channel.send.await_count == 1
    finally: await resource.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["read", "add_view", "no_channel"])
async def test_optional_start_failure_cleans_owned_state_without_core_failure(panel, failure):
    await panel.resource.stop()
    channel = None if failure == "no_channel" else 42
    resource = OperationsPanel(panel.bot, master=1, channel=channel, state=panel.tmp_path, inbox=panel.inbox,
        status=panel.status, clock=panel.clock, supervisor=panel.supervisor, executor=panel.executor)
    if failure == "read": resource.store.read = Mock(side_effect=PermissionError("private"))
    if failure == "add_view": panel.bot.add_view = Mock(side_effect=RuntimeError("private"))
    await resource.start()
    assert resource.closed and not resource.tasks
    assert resource.startup_cleanup_complete
    assert "on_ready" not in panel.listeners
    assert resource.gauges()["operations_panel_enabled"] == 0
    if resource.view is not None: assert resource.view.is_finished()


@pytest.mark.asyncio
async def test_atomic_confirmed_request_refuses_stale_revision_and_replay(tmp_path):
    executor = BoundedExecutor(workers=2, queue_capacity=2, name="manual-panel-test")
    (tmp_path/"audit").mkdir()
    inbox = RequestInbox(tmp_path,tmp_path/"lock",executor,Audit(tmp_path/"audit"),"r-test")
    try:
        before = await inbox.snapshot()
        assert await inbox.accept_current("restart","one",before["revision"]) == "accepted"
        assert await inbox.accept_current("update","two",before["revision"]) == "stale"
        row = read_json(tmp_path/"manual-request.json"); row["result"] = "ok"; atomic_json(tmp_path/"manual-request.json",row)
        after = await inbox.snapshot()
        assert await inbox.accept_current("restart","one",after["revision"]) == "already_running"
        assert len(list((tmp_path/"audit").iterdir())) == 1
    finally: await executor.close(grace_seconds=2)


@pytest.mark.asyncio
async def test_status_reader_exports_allowlist_and_known_terminal_result(tmp_path):
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="status-test")
    inbox = SimpleNamespace(state=tmp_path,executor=executor,snapshot=AsyncMock(return_value={"operation":None,"result":None,"revision":"a"*64}))
    outcome = {"id":"b"*32,"operation":"update","result":"ok","stage":"complete","timestamp":"2026-10-30T10:00:00+09:00",
               "token":"SECRET","path":"/private/user","message":"private"}
    try:
        status = OperationalStatus(inbox,SimpleNamespace(enabled=AsyncMock(return_value=False)),"r-test",lambda:True,lambda _:outcome)
        snapshot = await status.snapshot(); rendered = str(status_embed(snapshot).to_dict())
        assert snapshot["outcome"] == {"id":"b"*32,"operation":"update","result":"ok","stage":"complete","timestamp":"2026-10-30T01:00:00Z"}
        assert not snapshot["consumer_enabled"]
        for s in ["SECRET","private","/private"]: assert s not in rendered
        outcome["result"] = "secret text"
        with pytest.raises(ValidationError): await status.snapshot()
    finally: await executor.close(grace_seconds=2)


@pytest.mark.asyncio
async def test_historical_started_record_is_not_asserted_running_and_stays_blocked(tmp_path):
    executor=BoundedExecutor(workers=1,queue_capacity=2,name="old-result-test")
    inbox=SimpleNamespace(state=tmp_path,executor=executor,snapshot=AsyncMock(return_value={"operation":None,"result":None,"revision":"a"*64}))
    outcome={"id":"b"*32,"operation":"update","result":"in_progress","stage":"readiness","timestamp":"2020-01-01T10:00:00+09:00",
             "message":"PRIVATE_SECRET","path":"/private/user","source":"PRIVATE_SOURCE"}
    try:
        status=OperationalStatus(inbox,SimpleNamespace(enabled=AsyncMock(return_value=True)),"r-test",lambda:True,lambda _:outcome)
        snapshot=await status.snapshot();description=status_embed(snapshot).description
        assert snapshot["pending"] is True
        assert "시작 기록·완료 미확인 (운영 확인 필요)" in description
        assert "진행 중" not in description
        assert "2020-01-01T01:00:00Z" in description and "준비 확인" in description
        for raw in ["PRIVATE_SECRET","PRIVATE_SOURCE","/private/user","2020-01-01T10:00:00+09:00"]:
            assert raw not in description
    finally:await executor.close(grace_seconds=2)


@pytest.mark.asyncio
async def test_request_without_recorded_time_remains_time_unknown_and_completion_unconfirmed(tmp_path):
    executor=BoundedExecutor(workers=1,queue_capacity=2,name="unknown-time-test")
    inbox=SimpleNamespace(state=tmp_path,executor=executor,snapshot=AsyncMock(return_value={"operation":"restart","result":"in_progress","revision":"a"*64}))
    try:
        status=OperationalStatus(inbox,SimpleNamespace(enabled=AsyncMock(return_value=True)),"r-test",lambda:True)
        snapshot=await status.snapshot();description=status_embed(snapshot).description
        assert snapshot["pending"] is True
        assert "요청 기록(시각 미상): 재시작 · 시작 기록·완료 미확인" in description
        assert "결과 기록 시각(UTC): 확인되지 않음" in description
        assert "진행 중" not in description
    finally:await executor.close(grace_seconds=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("timestamp",None),("timestamp","2020-01-01T10:00:00"),
    ("timestamp","PRIVATE_TIMESTAMP token=secret"),("timestamp","0001-01-01T00:00:00+01:00"),
    ("timestamp","x"*41),("stage",None),("stage","PRIVATE_STAGE"),("stage","``` @everyone")])
async def test_bad_private_or_overflowing_record_time_stage_fail_closed(tmp_path,field,value):
    executor=BoundedExecutor(workers=1,queue_capacity=2,name="bad-result-test")
    inbox=SimpleNamespace(state=tmp_path,executor=executor,snapshot=AsyncMock(return_value={"operation":None,"result":None,"revision":"a"*64}))
    outcome={"id":"b"*32,"operation":"update","result":"in_progress","stage":"readiness","timestamp":"2020-01-01T01:00:00Z"}
    outcome[field]=value
    try:
        status=OperationalStatus(inbox,SimpleNamespace(enabled=AsyncMock(return_value=True)),"r-test",lambda:True,lambda _:outcome)
        with pytest.raises(ValidationError) as error:await status.snapshot()
        assert "PRIVATE" not in str(error.value) and "secret" not in str(error.value)
    finally:await executor.close(grace_seconds=2)


@pytest.mark.asyncio
async def test_application_reauthorizes_at_write_boundary():
    port = SimpleNamespace(accept_current=AsyncMock(return_value="accepted"))
    service = ManualOperations(1,port)
    assert await service.confirmed(2,"restart","nonce","a"*64) == "forbidden"
    assert await service.confirmed(True,"restart","nonce","a"*64) == "forbidden"
    assert await service.confirmed(1,"arbitrary","nonce","a"*64) == "invalid"
    port.accept_current.assert_not_awaited()


def test_timer_adapter_only_uses_fixed_readonly_command(monkeypatch):
    run = Mock(return_value=SimpleNamespace(returncode=0,stdout="ActiveState=active\nUnitFileState=enabled\n"))
    monkeypatch.setattr("discordbot.operations.adapters.discord_admin.subprocess.run",run)
    adapter = SystemdManualConsumer(None)
    assert adapter._enabled()
    assert run.call_args.args[0] == ["systemctl","show","discordbot-manual.timer","--property=ActiveState,UnitFileState"]
    run.return_value.stdout = "ActiveState=inactive\nUnitFileState=disabled\n"
    assert not adapter._enabled()
    run.side_effect = PermissionError("private")
    assert not adapter._enabled()


def test_corrupt_panel_and_request_metadata_fail_closed(tmp_path):
    atomic_json(tmp_path/"operations-panel.json", {"version":1,"channel":99,"message":444,"nonce":"a"*24,"state":"published"})
    with pytest.raises(ValidationError): PanelStore(tmp_path,42).read()
    inbox = RequestInbox(tmp_path,tmp_path/"lock",None,None,"r-test")
    atomic_json(tmp_path/"manual-request.json", {"operation":"shell","result":"pending","receipt":"a"*64})
    with pytest.raises(ValidationError): inbox._snapshot()
