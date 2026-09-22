"""Private inherited-channel worker and explicit bounded asyncio loop owner."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import signal
import struct
import sys
import time

from discordbot.composition.guardian import WorkerControl, receive_control
from discordbot.platform.tasks import LifecycleTasks


def run_managed(application: Callable[[WorkerControl], Awaitable[None]], control: WorkerControl) -> int:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    owner = LifecycleTasks()
    failed = False
    main: asyncio.Task | None = None
    stop_requested = False

    def stop(epoch: float | None = None) -> None:
        nonlocal stop_requested
        control.stopping(epoch)
        if not stop_requested and main is not None and not main.done():
            main.cancel()
        stop_requested = True

    def message() -> None:
        try:
            packet = control.channel.recv(64)
        except BlockingIOError:
            return
        if len(packet) == 9 and packet[:1] == b"T":
            stamp = struct.unpack("!d", packet[1:])[0]
            stop(min(time.monotonic(), stamp))
        else:
            control.failed = True
            stop()

    old = {sig: signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop))
           for sig in (signal.SIGTERM, signal.SIGINT)}
    loop.add_reader(control.channel.fileno(), message)

    async def execute() -> None:
        nonlocal main, failed
        main = owner.start(application(control), name="application-main")
        try:
            while not main.done():
                if control.epoch is not None and loop.time() >= control.epoch + control.policy.grace:
                    failed = True
                    control.send(b"A")
                    main.cancel()
                    break
                await asyncio.wait({main}, timeout=.005)
            if main.done():
                main.result()
        except BaseException:
            failed = True
            control.send(b"F")
        finally:
            control.stopping()

    async def finalize() -> bool:
        deadline = control.stopping() + control.policy.loop
        pending = {task for task in asyncio.all_tasks(loop) if task is not asyncio.current_task() and not task.done()}
        for task in pending:
            task.cancel()
        if pending:
            done, pending = await asyncio.wait(pending, timeout=max(0, deadline-loop.time()))
            for task in done:
                if not task.cancelled():
                    task.exception()
        if pending:
            return False
        try:
            await owner.run(loop.shutdown_asyncgens(), name="async-generator-close", deadline=deadline)
            await owner.run(loop.shutdown_default_executor(), name="default-executor-close", deadline=deadline)
        except (Exception, asyncio.CancelledError):
            return False
        return not owner.pending

    try:
        loop.run_until_complete(execute())
        clean_loop = loop.run_until_complete(finalize())
        if not clean_loop:
            control.send(b"L")
            # Do not discard live task/thread/finalizer ownership or enter an
            # unbounded Python cleanup fallback. The independent guardian kills
            # this process at T0+(H-G), even if the loop itself stopped working.
            while True:
                signal.pause()
        if failed or control.failed:
            control.send(b"F")
            return 1
        control.send(b"C")
        return 0
    finally:
        loop.remove_reader(control.channel.fileno())
        loop.close()
        asyncio.set_event_loop(None)
        for sig, handler in old.items():
            signal.signal(sig, handler)
        # Keep the control FD until interpreter exit: a thread join after this
        # function returns must remain under the guardian's stop clock.


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    control = receive_control(int(args.pop(0)))
    from discordbot.composition.main import worker_main
    return worker_main(args, control)


if __name__ == "__main__":
    raise SystemExit(main())
