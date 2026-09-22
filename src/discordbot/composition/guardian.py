"""Synchronous Linux service owner. No application imports, threads or log pipes."""

from __future__ import annotations

import ctypes
import logging
import os
import select
import signal
import socket
import struct
import subprocess
import sys
import time
from collections.abc import Callable, Sequence

from discordbot.platform.termination import TerminationPolicy

logger = logging.getLogger(__name__)


def _prctl(option: int, value: int) -> None:
    if ctypes.CDLL(None, use_errno=True).prctl(option, value, 0, 0, 0):
        raise OSError(ctypes.get_errno(), "process containment setup failed")


def _signal_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return  # Already exited; never fall back to name matching.


def _group_exists(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def supervise(command: Callable[[int], Sequence[str]], *,
              policy: TerminationPolicy = TerminationPolicy(),
              event: Callable[[str], None] | None = None) -> int:
    """Exactly one worker. Injected policy/command are for explicit test callers.

    Production CLI exposes neither. Systemd owns descendants escaping the process
    group and also owns cleanup if this guardian dies.
    """
    if sys.platform != "linux":
        logger.error("guardian.linux_containment_required")
        return 1
    _prctl(36, 1)  # PR_SET_CHILD_SUBREAPER: collect orphaned group descendants.
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    parent.setblocking(False)
    worker: subprocess.Popen | None = None
    epoch: float | None = None
    failed = False
    forced = False
    ready = False
    complete = False
    eof = False
    requested = False
    stop_sent = False
    exit_observed = False
    # Datagram telemetry cannot block the guardian on application logging I/O.
    journal = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    journal.setblocking(False)

    def emit(name: str) -> None:
        # Fixed labels only; no configuration, exception text or arbitrary worker data.
        if event is not None:
            event(name)
        try:
            journal.sendto(("<27>discordbot: " + name).encode("ascii"), "/dev/log")
        except OSError:
            return  # Missing/full local log sink must not affect containment.

    def request(*_: object) -> None:
        nonlocal requested
        requested = True

    old = {sig: signal.signal(sig, request) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        started = time.monotonic()
        worker = subprocess.Popen(list(command(child.fileno())), pass_fds=(child.fileno(),),
                                  start_new_session=True, close_fds=True)
        child.close()
        parent.send(struct.pack("!cddd", b"I", policy.startup, policy.grace, policy.reap))
        emit("guardian.started")
        while True:
            now = time.monotonic()
            if not eof:
                for _ in range(8):  # Bounded control work per deadline observation.
                    try:
                        packet = parent.recv(64)
                    except BlockingIOError:
                        break
                    except ConnectionResetError:
                        packet = b""  # A force-killed peer may leave unread stop data.
                    if not packet:
                        eof = True
                        if not complete:
                            failed = True
                            emit("guardian.control_lost")
                        requested = True
                        break
                    if packet == b"S":
                        ready = True
                        emit("guardian.ready")
                    elif packet == b"C":
                        complete = True
                        requested = True
                    elif packet in (b"F", b"A", b"L"):
                        failed = True
                        requested = True
                        emit({b"F": "worker.failed", b"A": "worker.application_timeout", b"L": "worker.loop_timeout"}[packet])
                    elif len(packet) == 9 and packet[:1] == b"T":
                        stamp = struct.unpack("!d", packet[1:])[0]
                        if not started <= stamp <= now:
                            stamp = now
                        epoch = min(epoch, stamp) if epoch is not None else stamp
                        requested = True
                    else:
                        failed = True
                        requested = True
            code = worker.poll()  # Reaps only the direct worker first.
            if code is not None:
                if not exit_observed:
                    exit_observed = True
                    if code != 0 and not failed:
                        emit("guardian.worker_crash")
                if code != 0 or not complete or not ready:
                    failed = True
                requested = True
                # Reap only our process group, never unrelated children.
                while True:
                    try:
                        pid, _ = os.waitpid(-worker.pid, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if pid == 0:
                        break
                if not _group_exists(worker.pid):
                    emit("guardian.forced" if forced else "guardian.failed" if failed else "guardian.clean")
                    return 1 if failed or forced else 0
            if not ready and now >= started + policy.startup:
                if not requested:
                    emit("guardian.startup_timeout")
                failed = True
                requested = True
            if requested and epoch is None:
                epoch = now
            if epoch is not None:
                if not stop_sent:
                    # One stop transaction; repeated signals never reset T0.
                    stop_sent = True
                    try:
                        parent.send(b"T" + struct.pack("!d", epoch))
                    except (BrokenPipeError, BlockingIOError, ConnectionResetError):
                        pass  # Signal and independent deadlines remain armed.
                    if code is None:
                        try:
                            worker.send_signal(signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    emit("guardian.stopping")
                if now >= epoch + policy.kill and not forced:
                    _signal_group(worker.pid, signal.SIGKILL)
                    failed = forced = True
                    emit("guardian.escalation")
                if now >= epoch + policy.reap:
                    emit("guardian.reap_failed")
                    return 1
            if eof:
                time.sleep(.005)
            else:
                select.select([parent], [], [], .005)
    finally:
        if worker is not None and _group_exists(worker.pid):
            _signal_group(worker.pid, signal.SIGKILL)
            try:
                remaining = policy.grace if epoch is None else max(0, epoch + policy.reap - time.monotonic())
                worker.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                emit("guardian.reap_failed")
        parent.close()
        child.close()
        journal.close()
        for sig, handler in old.items():
            signal.signal(sig, handler)


class WorkerControl:
    def __init__(self, channel: socket.socket, policy: TerminationPolicy) -> None:
        self.channel = channel
        self.policy = policy
        self.epoch: float | None = None
        self.failed = False

    def send(self, packet: bytes) -> None:
        try:
            self.channel.send(packet)
        except (BlockingIOError, BrokenPipeError, ConnectionResetError):
            self.failed = True  # Guardian sees EOF/exit or its startup/stop timeout.

    def stopping(self, epoch: float | None = None) -> float:
        stamp = time.monotonic() if epoch is None else epoch
        self.epoch = min(self.epoch, stamp) if self.epoch is not None else stamp
        self.send(b"T" + struct.pack("!d", self.epoch))
        return self.epoch


def receive_control(fd: int) -> WorkerControl:
    """A flag is insufficient: require an inherited socket owned by the parent."""
    channel = socket.socket(fileno=fd)
    channel.set_inheritable(False)
    if channel.family != socket.AF_UNIX or channel.type != socket.SOCK_SEQPACKET:
        raise ValueError("private worker channel required")
    parent = os.getppid()
    peer, uid, _ = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if peer != parent or uid != os.getuid() or parent == 1:
        raise ValueError("worker channel is not owned by its guardian")
    _prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG, then close the parent-death race.
    if os.getppid() != parent:
        raise RuntimeError("guardian lost during worker startup")
    channel.settimeout(2)
    packet = channel.recv(64)
    tag, startup, grace, reap = struct.unpack("!cddd", packet)
    if tag != b"I":
        raise ValueError("invalid guardian handshake")
    channel.setblocking(False)
    return WorkerControl(channel, TerminationPolicy(startup, grace, reap))
