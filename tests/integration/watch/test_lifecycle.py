import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from .conftest import Socket
from discordbot.platform.errors import CapacityError, ConflictError, DatabaseUnavailableError, ShutdownError, DeadlineExceededError
from discordbot.watch.application.service import WatchService
from discordbot.watch.domain.policy import ClosedSession, InvalidCapability, WatchLimits
from .test_runtime import advance

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("seconds,closed", [(29.999, False), (30, False), (34.999, False), (35, True)])
async def test_no_participant_creation_grace_boundary(service, invite, clock, seconds, closed):
    actor = service.resolve(invite.capability)
    await advance(service, clock, seconds)
    assert actor.closed is closed
    assert bool(service.sessions) is not closed


async def test_absolute_expiry_revokes_even_connected_capability(service, invite, clock):
    actor, peer = await service.connect(invite.capability, Socket())
    actor.intent = replace(actor.intent, expires=service.now()+6)
    await advance(service, clock, 6)
    assert actor.closed and not actor.peers
    with pytest.raises(InvalidCapability):
        service.resolve(invite.capability)


async def test_abort_before_late_create_is_a_durable_tombstone(service, clock):
    data = (100, 42, "late-create", int(service.now()))
    await service.abort(*data)
    with pytest.raises(ClosedSession):
        await service.create(*data)
    assert not service.sessions


async def test_create_cancel_after_commit_compensates_and_cannot_retry(service, clock):
    entered, release = asyncio.Event(), asyncio.Event()
    original = service.writer.create
    async def create(*args):
        result = await original(*args)
        entered.set()
        await release.wait()
        return result
    service.writer.create = create
    data = (100, 42, "cancelled-create", int(service.now()))
    task = asyncio.create_task(service.create(*data))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    service.writer.create = original
    with pytest.raises(ClosedSession):
        await service.create(*data)
    assert not service.sessions


async def test_stale_cleanup_readiness_barrier_and_failure(service, clock):
    entered, release = asyncio.Event(), asyncio.Event()
    other = WatchService(service.writer, service.capability, service.metadata, WatchLimits(), clock, service.ids, service.telemetry)
    original = service.writer.start
    async def blocked(*args):
        entered.set()
        await release.wait()
        raise DatabaseUnavailableError("synthetic stale failure")
    service.writer.start = blocked
    task = asyncio.create_task(other.start())
    await entered.wait()
    assert not other.ready()
    with pytest.raises(ShutdownError):
        await other.create(100, 42, "before-ready", int(service.now()))
    release.set()
    with pytest.raises(DatabaseUnavailableError):
        await task
    assert not other.ready()
    service.writer.start = original
    await other.stop()


async def test_new_owner_cleans_dead_owner_and_old_peer_cannot_mutate(service, invite, clock):
    actor, peer = await service.connect(invite.capability, Socket())
    await actor.call("bind", 1000, 500, False)
    clock.advance(10)
    other = WatchService(service.writer, service.capability, service.metadata, WatchLimits(), clock, service.ids, service.telemetry)
    await other.start()
    try:
        assert other.ready()
        with pytest.raises(ShutdownError):
            await actor.call("message", peer.id, {"type": "chat", "text": "late"})
        pending = await other.writer.cleanup(other.epoch, other.now())
        assert pending[0].message == 500
        new = await other.create(200, 43, "new-owner", int(other.now()))
        await service.sweep()
        assert not service.ready()
        assert other.resolve(new.capability)
    finally:
        await other.stop()


async def test_mailbox_saturation_cancelled_waiter_and_close_are_bounded(service, clock):
    service.limits = replace(service.limits, mailbox=2)
    invite = await service.create(100, 42, "mailbox", int(service.now()))
    actor = service.resolve(invite.capability)
    entered, release = asyncio.Event(), asyncio.Event()
    original = service.writer.add
    async def blocked(*args):
        entered.set()
        await release.wait()
        return await original(*args)
    service.writer.add = blocked
    adding = asyncio.create_task(service.add(invite.capability, "https://youtu.be/aaaaaaaaaaa", "A"))
    await entered.wait()
    leaving = asyncio.create_task(actor.call("leave", "absent"))
    closing = asyncio.create_task(actor.call("close"))
    await asyncio.sleep(0)
    with pytest.raises(CapacityError):
        await actor.call("connect", Socket())
    leaving.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leaving
    release.set()
    await asyncio.gather(adding, closing)
    assert actor.closed and actor.mailbox.empty()


async def test_add_metadata_late_result_cannot_revive_closed_session(service, invite):
    entered, release = asyncio.Event(), asyncio.Event()
    async def title(_):
        entered.set()
        await release.wait()
        return "Synthetic late title"
    service.metadata.title = title
    task = asyncio.create_task(service.add(invite.capability, "https://youtu.be/aaaaaaaaaaa", "A"))
    await entered.wait()
    await service.close(invite.session_id)
    release.set()
    with pytest.raises(ClosedSession):
        await task
    assert not service.sessions


async def test_session_cap_and_maintenance_schedule_idempotence(service, clock):
    for number in range(8):
        await service.create(100+number, 42, str(number), int(service.now()))
    with pytest.raises(CapacityError):
        await service.create(100, 42, "full", int(service.now()))
    service.schedule()
    task = service._maintenance
    service.schedule()
    service.schedule()
    assert service._maintenance is task
    await service.stop()
    assert not service.supervisor.snapshot().active


async def test_total_connections_playlist_and_client_rate_caps(service, clock):
    service.limits = replace(service.limits, total_clients=2, playlist=2)
    first = await service.create(100, 42, "first", int(service.now()))
    second = await service.create(200, 42, "second", int(service.now()))
    actor, peer = await service.connect(first.capability, Socket())
    await service.connect(second.capability, Socket())
    with pytest.raises(CapacityError):
        await service.connect(second.capability, Socket())
    for letter in "ab":
        await service.add(first.capability, "https://youtu.be/"+letter*11, "A")
    with pytest.raises(CapacityError):
        await service.add(first.capability, "https://youtu.be/ccccccccccc", "A")
    for _ in range(10):
        await actor.call("message", peer.id, {"type": "chat", "text": "bounded"})
    with pytest.raises(CapacityError):
        await actor.call("message", peer.id, {"type": "chat", "text": "excess"})


async def test_expired_queued_work_never_creates_a_peer(service, invite, clock):
    actor = service.resolve(invite.capability)
    entered, release = asyncio.Event(), asyncio.Event()
    original = service.writer.playlist
    async def blocked(*args):
        entered.set()
        await release.wait()
        return await original(*args)
    service.writer.playlist = blocked
    reading = asyncio.create_task(actor.call("playlist"))
    await asyncio.wait_for(entered.wait(), 2)
    joining = asyncio.create_task(actor.call("connect", Socket()))
    await asyncio.sleep(0)
    clock.tick += 6
    release.set()
    await reading
    with pytest.raises(DeadlineExceededError):
        await joining
    assert not actor.peers


async def test_close_during_durable_create_cannot_leave_an_orphan_actor(service):
    entered, release = asyncio.Event(), asyncio.Event()
    original = service.writer.create
    data = (100, 42, "create-close", int(service.now()))
    _, sid = service.capability.mint(*data)
    async def blocked(*args):
        result = await original(*args)
        entered.set()
        await release.wait()
        return result
    service.writer.create = blocked
    creating = asyncio.create_task(service.create(*data))
    await asyncio.wait_for(entered.wait(), 2)
    closing = asyncio.create_task(service.close(sid))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(creating, closing)
    assert not service.sessions
    await asyncio.sleep(0)
    assert not service.supervisor.snapshot().active
