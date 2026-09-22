"""Offline subprocess fixture; production has no selector for these scenarios."""

from pathlib import Path
import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
from discordbot.composition.guardian import receive_control, supervise
from discordbot.composition.main import run_process
from discordbot.composition.runtime import ProcessRuntime
from discordbot.composition.worker import run_managed
from discordbot.platform.tasks import TaskSpec, CancellationBehavior
from discordbot.platform.termination import TerminationPolicy


def record(directory, name, **fields):
    with (directory / (name + '.json')).open('w') as stream:
        json.dump({'pid': os.getpid(), **fields}, stream)


async def resistant(directory):
    record(directory, 'armed')
    while True:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            record(directory, 'resisted')


def main():
    role, mode, path, *extra = sys.argv[1:]
    directory = Path(path)
    if role == 'descendant':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        depth = int(extra[0])
        record(directory, 'descendant-' + str(depth), pgid=os.getpgrp())
        if depth:
            subprocess.Popen([sys.executable, '-I', '-B', __file__, 'descendant', mode, path, '0'], close_fds=True)
        while True:
            signal.pause()
    if role == 'guardian':
        record(directory, 'guardian')
        def event(name):
            with (directory / 'events').open('a') as stream:
                stream.write(name + '\n')
            with (directory / 'timings').open('a') as stream:
                stream.write(json.dumps({'name': name, 'time': time.monotonic()}) + '\n')
        result = supervise(lambda fd: [sys.executable, '-I', '-B', __file__, 'worker', mode, path, str(fd)],
                           policy=TerminationPolicy(.6, .15, .9), event=event)
        record(directory, 'result', code=result)
        return result
    control = receive_control(int(extra[0]))
    record(directory, 'worker', pgid=os.getpgrp(), ppid=os.getppid())
    while not (directory / 'go').exists():
        time.sleep(.001)

    config = PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, 'synthetic', runtime=control.policy.runtime())
    runtime = ProcessRuntime(config=config)

    class Resource:
        required = True
        name = 'synthetic-resource'

        async def start(self):
            if mode == 'startup':
                await resistant(directory)
            if mode == 'rollback':
                return
            if mode in ('task', 'capacity'):
                count = config.limits.task_capacity if mode == 'capacity' else 1
                for index in range(count):
                    runtime.supervisor.start(TaskSpec('hostile', 'test', str(index), 'one', 30,
                        cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN),
                        lambda: resistant(directory) if mode == 'task' else asyncio.sleep(30))
                await asyncio.sleep(0)
            if mode in ('thread', 'retained'):
                started = threading.Event()
                def block():
                    started.set()
                    threading.Event().wait(30)
                dispatch = runtime.executor.run_retained if mode == 'retained' else runtime.executor.run
                runtime.supervisor.start(TaskSpec('thread', 'test', 'one', 'one', 30,
                    cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), lambda: dispatch(block))
                while not started.is_set():
                    await asyncio.sleep(.001)
            if mode == 'default-executor':
                started = threading.Event()
                def block():
                    started.set()
                    threading.Event().wait(30)
                runtime.supervisor.start(TaskSpec('default-thread', 'test', 'one', 'one', 30,
                    cancellation_behavior=CancellationBehavior.CANCEL_ON_SHUTDOWN), lambda: asyncio.to_thread(block))
                while not started.is_set():
                    await asyncio.sleep(.001)
            if mode == 'interpreter':
                started = threading.Event()
                def block():
                    started.set()
                    threading.Event().wait(30)
                threading.Thread(target=block, daemon=False).start()
                while not started.is_set():
                    await asyncio.sleep(.001)
            if mode in ('tree', 'internal-tree', 'escape', 'internal-restart', 'parent-death'):
                subprocess.Popen([sys.executable, '-I', '-B', __file__, 'descendant', mode, path, '1'],
                                 start_new_session=mode in ('escape', 'internal-restart'), close_fds=True)
                while not (directory / 'descendant-0.json').exists():
                    await asyncio.sleep(.001)
            if mode in ('asyncgen', 'asyncgen-error'):
                async def generator():
                    try:
                        yield 1
                    finally:
                        if mode == 'asyncgen-error':
                            raise RuntimeError('synthetic async-generator close failure')
                        await resistant(directory)
                self.generator = generator()
                await anext(self.generator)
            record(directory, 'armed')

        async def stop(self):
            if mode in ('resource', 'rollback'):
                await resistant(directory)
            if mode == 'close-error':
                raise RuntimeError('synthetic close failure')
            record(directory, 'resource-stopped')

    resource = Resource()
    runtime = ProcessRuntime(config=config, resources=(resource,))
    if mode.startswith('optional-'):
        class Optional:
            name, required = 'optional', False
            async def start(self):
                raise RuntimeError('synthetic optional failure')
            async def stop(self):
                assert not (directory / 'optional-stopped.json').exists()
                if mode == 'optional-resistant':
                    await resistant(directory)
                record(directory, 'optional-stopped')
        runtime = ProcessRuntime(config=config, resources=(resource, Optional()))
    if mode == 'rollback':
        class Broken:
            name, required = 'broken', True
            async def start(self):
                raise RuntimeError('synthetic startup failure')
            async def stop(self):
                return
        runtime = ProcessRuntime(config=config, resources=(resource, Broken()))

    class Component:
        async def start(self):
            return
        async def stop(self):
            return
        def flush(self):
            record(directory, 'flushed')

    class Listener(Component):
        async def start(self):
            if mode == 'optional-degraded':
                assert runtime.health.snapshot().ready
                assert len(runtime._started_resources) == 1
                assert not (directory / 'resource-stopped.json').exists()
                record(directory, 'degraded-ready')
            if mode in ('internal-tree', 'escape', 'internal-restart', 'crash'):
                raise RuntimeError('synthetic internal failure')
            if mode == 'blocked-loop':
                # Started marker is absent; guardian startup timeout must still work.
                record(directory, 'armed')
                time.sleep(30)

    assembly = ModuleType('discordbot.composition.production_watch')
    assembly.assemble = lambda *_: (runtime, None, Listener(), Component(), Component())
    sys.modules[assembly.__name__] = assembly
    result = run_managed(lambda channel: run_process(config, None, channel), control)
    record(directory, 'worker-returned', code=result)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
