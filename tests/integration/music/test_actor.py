import asyncio

import pytest

from discordbot.music.domain.model import Bounds, LoopMode
from discordbot.platform.errors import CapacityError, ConflictError
from .conftest import settle, song

pytestmark = pytest.mark.asyncio


async def playing(actor, tracks=None):
    await actor.ask("connect", channel_id=123)
    await actor.ask("enqueue", tracks=tracks or (song(), song(2)))
    await settle(lambda: actor.projection().status == "playing")
    return actor.projection()


async def test_cf01_cf02_cf03_skip_retry_late_callback(rig):
    make, clock, sleeper, audio, library, provider, repo, _ = rig
    actor = make()
    first = await playing(actor)
    await actor.ask("ended", attempt=first.attempt, failed=True)
    assert actor.projection().retry_at == 103
    await settle(lambda: bool(sleeper.pending))
    results = await asyncio.gather(actor.ask("skip", session_id=first.session_id),
                                   actor.ask("skip", session_id=first.session_id),
                                   actor.ask("ended", attempt=first.attempt, failed=True))
    assert results.count(True) == 1
    sleeper.wake(3)
    await settle(lambda: actor.projection().status == "playing")
    assert actor.projection().current.item_id == "2"
    assert repo.record_start.await_count == 2


async def test_retry_exact_3_8_third_skip(rig):
    make, clock, sleeper, audio, library, provider, repo, _ = rig
    actor = make()
    await playing(actor)
    session = actor.projection().session_id
    for delay in (3, 8):
        attempt = actor.projection().attempt
        await actor.ask("ended", attempt=attempt, failed=True)
        assert actor.projection().retry_at == clock.value + delay
        await settle(lambda: any(n == delay for n, _ in sleeper.pending))
        clock.value += delay
        sleeper.wake(delay)
        await settle(lambda: actor.projection().status == "playing")
        assert actor.projection().session_id == session
    await actor.ask("ended", attempt=actor.projection().attempt, failed=True)
    await settle(lambda: actor.projection().status == "playing")
    assert actor.projection().current.item_id == "2"
    assert {call.args[1] for call in repo.record_start.await_args_list[:3]} == {session}


async def test_cf01_skip_during_preparation(rig):
    make, _, _, _, library, _, repo, _ = rig
    entered, release = asyncio.Event(), asyncio.Event()
    original = library.acquire.side_effect
    async def acquire(track):
        if track.item_id == "1":
            entered.set()
            await release.wait()
        return original(track)
    library.acquire.side_effect = acquire
    actor = make()
    await actor.ask("connect", channel_id=1)
    await actor.ask("enqueue", tracks=(song(), song(2)))
    await entered.wait()
    await actor.ask("skip", session_id=actor.projection().session_id)
    release.set()
    await settle(lambda: actor.projection().status == "playing")
    assert actor.projection().current.item_id == "2"
    assert repo.record_start.await_count == 1


@pytest.mark.parametrize("mode,expected", [(LoopMode.NONE, "2"), (LoopMode.SONG, "1"), (LoopMode.QUEUE, "2")])
async def test_loop_end_and_manual_skip(rig, mode, expected):
    actor = rig[0]()
    first = await playing(actor)
    for _ in range(mode.value): await actor.ask("loop")
    await actor.ask("ended", attempt=first.attempt, failed=False)
    await settle(lambda: actor.projection().status == "playing")
    assert actor.projection().current.item_id == expected
    assert actor.projection().session_id != first.session_id
    if mode == LoopMode.QUEUE: assert actor.projection().queue[-1].item_id == "1"


async def test_pause_elapsed_reconnect_preserves_session_and_pause(rig):
    make, clock, sleeper, _, _, _, repo, _ = rig
    actor = make()
    first = await playing(actor)
    clock.value += 17
    await actor.ask("pause", session_id=first.session_id)
    clock.value += 40
    assert actor.projection().elapsed == 17
    await actor.ask("pause", session_id=first.session_id)
    await actor.ask("disconnected")
    await settle(lambda: any(n == 8 for n, _ in sleeper.pending))
    await actor.ask("connect", channel_id=123)
    sleeper.wake(8)
    await settle(lambda: actor.projection().status == "paused")
    assert actor.projection().elapsed == 17
    await actor.ask("resume", session_id=first.session_id)
    clock.value += 3
    assert actor.projection().elapsed == 20
    assert {call.args[1] for call in repo.record_start.await_args_list} == {first.session_id}


async def test_cf04_autoplay_manual_enqueue_invalidates_late_result(rig):
    make, _, _, _, _, provider, _, _ = rig
    entered, release = asyncio.Event(), asyncio.Event()
    async def lookup(*args, **kwargs):
        entered.set()
        await release.wait()
        return (song(9, "Fresh recommendation"),)
    provider.lookup.side_effect = lookup
    actor = make()
    first = await playing(actor, (song(),))
    await actor.ask("autoplay", enabled=True)
    await actor.ask("ended", attempt=first.attempt, failed=False)
    await entered.wait()
    await actor.ask("enqueue", tracks=(song(2),))
    release.set()
    await settle(lambda: actor.projection().status == "playing")
    assert actor.projection().current.item_id == "2"
    assert not actor.projection().queue


async def test_autoplay_success_and_history_filter(rig):
    make, _, _, _, _, provider, _, _ = rig
    provider.lookup.return_value = (song(7, "Track 1 (Official)"), song(8, "Different melody"))
    actor = make()
    first = await playing(actor, (song(),))
    await actor.ask("autoplay", enabled=True)
    await actor.ask("ended", attempt=first.attempt, failed=False)
    await settle(lambda: actor.projection().status == "playing")
    assert actor.projection().current.item_id == "8"
    assert provider.lookup.call_args.args[0] == "ytsearch10:Artist"


async def test_cf05_tts_completion_and_skip_never_resurrect_track(rig):
    actor = rig[0]()
    first = await playing(actor)
    await actor.ask("tts", text="친구님이 입장하셨습니다.")
    await settle(lambda: actor.projection().status == "tts")
    tts = actor.projection().attempt
    await asyncio.gather(actor.ask("skip", session_id=first.session_id),
                         actor.ask("ended", attempt=first.attempt, failed=False),
                         actor.ask("ended", attempt=tts, failed=False))
    await settle(lambda: actor.projection().status == "playing")
    assert actor.projection().current.item_id == "2"
    assert len(rig[6].record_start.await_args_list) == 2


async def test_tts_resume_keeps_logical_session(rig):
    actor = rig[0]()
    first = await playing(actor)
    await actor.ask("tts", text="입장")
    await settle(lambda: actor.projection().status == "tts")
    await actor.ask("ended", attempt=actor.projection().attempt, failed=False)
    await settle(lambda: actor.projection().status == "playing")
    assert actor.projection().session_id == first.session_id


async def test_empty_timer_cancel_on_join_and_reconnect_expiry(rig):
    actor = rig[0]()
    await playing(actor)
    await actor.ask("members", channel_id=123, count=0)
    await settle(lambda: any(n == 2 for n, _ in rig[2].pending))
    await actor.ask("members", channel_id=123, count=1)
    rig[2].wake(2)
    await actor.ask("inspect")
    assert actor.projection().current
    await actor.ask("disconnected")
    await settle(lambda: any(n == 8 for n, _ in rig[2].pending))
    rig[2].wake(8)
    await settle(lambda: actor.projection().current is None)


async def test_cf21_stable_queue_identity_and_guild_isolation(rig):
    a, b = rig[0](100), rig[0](200)
    tracks = tuple(song(i, "Duplicate title") for i in range(30))
    await asyncio.gather(a.ask("enqueue", tracks=tracks), b.ask("enqueue", tracks=(song(99),)))
    await a.ask("edit", action="move", item_id="29")
    await a.ask("edit", action="remove", item_id="1")
    with pytest.raises(ConflictError): await a.ask("edit", action="remove", item_id="1")
    assert a.projection().queue[0].item_id == "29"
    assert b.projection().current.item_id == "99"
    revision = a.projection().revision
    await a.ask("enqueue", tracks=(song(100),))
    with pytest.raises(ConflictError): await a.ask("edit", action="clear", revision=revision)


async def test_mailbox_and_queue_hard_cap(rig):
    actor = rig[0](bounds=Bounds(mailbox=1, queue=2))
    first = actor.post("enqueue", tracks=(song(), song(2)))
    with pytest.raises(CapacityError): actor.post("inspect")
    await first
    with pytest.raises(CapacityError): await actor.ask("enqueue", tracks=(song(3), song(4)))


async def test_lookup_order_duplicate_and_cancel(rig):
    make, _, _, _, _, provider, _, _ = rig
    entered, release = asyncio.Event(), asyncio.Event()
    async def lookup(query, requester_id, **kwargs):
        if query.endswith("first"):
            entered.set()
            await release.wait()
        return (song(1 if query.endswith("first") else 2),)
    provider.lookup.side_effect = lookup
    actor = make()
    one = await actor.ask("lookup", request_id="a", query="first", requester_id=10)
    await entered.wait()
    two = await actor.ask("lookup", request_id="b", query="second", requester_id=10)
    with pytest.raises(ConflictError): await actor.ask("lookup", request_id="a", query="first", requester_id=10)
    release.set()
    await asyncio.gather(one, two)
    assert actor.projection().current.item_id == "1"
    assert actor.projection().queue[0].item_id == "2"


async def test_restore_default_and_persisted_volume_current_before_queue(rig):
    actor = rig[0](volume=.35)
    await actor.ask("restore", identity="saved", data={"current_song": song().legacy(), "queue": [song(2).legacy()], "elapsed_seconds": 47})
    state = actor.projection()
    assert state.volume == .35 and state.elapsed == 47
    assert state.current.title == "Track 1" and state.queue[0].title == "Track 2"
    assert not await actor.ask("restore", identity="saved", data={})
    empty = rig[0](200)
    await empty.ask("restore", identity="legacy", data={})
    assert empty.projection().volume == .5
