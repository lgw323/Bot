import asyncio

import pytest

from discordbot.platform.errors import CapacityError, ConflictError, ValidationError
from discordbot.watch.adapters.writer import SqliteWatchWriter
from discordbot.watch.domain.policy import InvalidCapability, ClosedSession
from .conftest import Socket

pytestmark = pytest.mark.asyncio


async def advance(service, clock, seconds):
    while seconds > 0:
        step = min(5, seconds)
        clock.advance(step)
        await service.sweep()
        seconds -= step


async def test_durable_idempotency_and_revocation(service, invite, clock):
    again = await service.create(100, 42, "synthetic-operation", int(clock.now().timestamp()))
    assert again == invite
    await service.close(invite.session_id)
    await service.close(invite.session_id)
    with pytest.raises(InvalidCapability):
        service.resolve(invite.capability)
    with pytest.raises(ClosedSession):
        await service.create(100, 42, "synthetic-operation", int(clock.now().timestamp()))
    await advance(service, clock, 61)
    with pytest.raises(ValidationError):
        await service.create(100, 42, "synthetic-operation", int(clock.now().timestamp())-61)


async def test_active_owner_prevents_stale_cleanup(database, service, invite):
    other = SqliteWatchWriter(database)
    with pytest.raises(ConflictError):
        await other.start("another-owner", service.now())
    assert service.resolve(invite.capability)


async def test_seven_messages_order_and_session_isolation(service, invite, clock):
    a, b, other = Socket(), Socket(), Socket()
    actor, first = await service.connect(invite.capability, a)
    _, second = await service.connect(invite.capability, b)
    another = await service.create(200, 43, "other", int(service.now()))
    await service.connect(another.capability, other)
    await asyncio.gather(actor.call("message", first.id, {"type": "join", "username": "A"}),
                         actor.call("message", second.id, {"type": "join", "username": "B"}))
    for value in ({"type": "chat", "username": "spoof", "text": "hello"},
        {"type": "state_change", "state": "playing", "time": 1}, {"type": "seek", "time": 2},
        {"type": "sync_request"}, {"type": "sync_response", "playing": False, "time": 3},
        {"type": "playlist_change", "message": "changed"}):
        await actor.call("message", first.id, value)
    await asyncio.sleep(0)
    revisions = [m["revision"] for m in b.messages]
    assert revisions == sorted(set(revisions))
    assert next(m for m in b.messages if m["type"] == "chat")["username"] == "A"
    assert {m["type"] for m in b.messages} >= {"user_list", "chat", "state_change", "seek", "sync_request", "sync_response", "playlist_change"}
    assert not other.messages


async def test_creation_grace_and_reconnect_boundary(service, invite, clock):
    actor = service.resolve(invite.capability)
    await advance(service, clock, 30)
    assert not actor.closed
    await actor.call("tick")
    _, peer = await service.connect(invite.capability, Socket())
    await actor.call("leave", peer.id)
    await advance(service, clock, 4.99)
    _, peer = await service.connect(invite.capability, Socket())
    await actor.call("leave", peer.id)
    await advance(service, clock, 5)
    assert actor.closed
    with pytest.raises(InvalidCapability):
        service.resolve(invite.capability)


@pytest.mark.parametrize('playing', [False, True])
async def test_single_viewer_reload_hydrates_actor_playback(service, invite, clock, playing):
    actor, peer = await service.connect(invite.capability, Socket())
    await actor.call('message', peer.id, {'type':'join','username':'Before'})
    await actor.call('message', peer.id, {'type':'sync_response','playing':playing,
        'time':17,'videoId':'aaaaaaaaaaa'})
    await actor.call('leave', peer.id)
    await advance(service, clock, 4)
    socket = Socket()
    _, replacement = await service.connect(invite.capability, socket)
    await actor.call('message', replacement.id, {'type':'join','username':'After'})
    await asyncio.sleep(0)
    snapshots = [m for m in socket.messages if m['type']=='sync_response']
    assert len(snapshots)==1
    assert snapshots[0]['videoId']=='aaaaaaaaaaa'
    assert snapshots[0]['state']==('playing' if playing else 'paused')
    assert snapshots[0]['time']==(21 if playing else 17)
    assert next(m for m in socket.messages if m['type']=='user_list')['users']==['After']
    # A return probe receives a server response even without another browser.
    socket.messages.clear()
    await actor.call('message', replacement.id, {'type':'sync_request'})
    await asyncio.sleep(0)
    assert {m['type'] for m in socket.messages}=={'sync_response','user_list'}


async def test_playlist_duplicate_order_close_race(service, invite):
    actor = service.resolve(invite.capability)
    one, two = "https://youtu.be/aaaaaaaaaaa", "https://youtu.be/bbbbbbbbbbb"
    await service.add(invite.capability, one, "A")
    await service.add(invite.capability, two, "B")
    await service.add(invite.capability, one, "C")
    rows = await actor.call("playlist")
    assert [row.video_url for row in rows] == [two, one]
    results = await asyncio.gather(actor.call("close"), actor.call("remove", two),
        actor.call("connect", Socket()), return_exceptions=True)
    assert results[0] is None
    assert all(isinstance(result, ClosedSession) for result in results[1:])
    assert actor.closed and not actor.peers and actor.mailbox.empty()


async def test_slow_peer_queue_is_bounded_and_fast_peer_progresses(service, invite, clock):
    gate = asyncio.Event()
    slow, fast = Socket(gate), Socket()
    actor, source = await service.connect(invite.capability, Socket())
    _, lagging = await service.connect(invite.capability, slow)
    await service.connect(invite.capability, fast)
    for index in range(25):
        clock.tick += 1
        await actor.call("message", source.id, {"type": "chat", "text": str(index)})
    assert lagging.failed and lagging.queue.qsize() <= service.limits.outbound
    assert len(fast.messages) == 25
    gate.set()
    await lagging.task
    assert slow.codes == [4008]
    await actor.call("tick")
    assert lagging.id not in actor.peers


async def test_connection_capacity_and_shutdown(service, invite):
    sockets = [Socket() for _ in range(8)]
    for socket in sockets:
        await service.connect(invite.capability, socket)
    with pytest.raises(CapacityError):
        await service.connect(invite.capability, Socket())
    await service.stop()
    assert all(socket.codes == [4001] for socket in sockets)
    assert not service.sessions


async def test_slow_socket_send_deadline_closes_without_blocking_session(service, invite):
    slow = Socket(asyncio.Event())
    actor, source = await service.connect(invite.capability, Socket())
    _, peer = await service.connect(invite.capability, slow)
    await actor.call("message", source.id, {"type": "chat", "text": "deadline"})
    await asyncio.wait_for(peer.task, 2)
    assert slow.codes == [4008]
    assert not actor.closed
