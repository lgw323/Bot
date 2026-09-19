"""Apply the approved prebuilt release to the synthetic pair; observe for five minutes."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

COMMIT = "63c77229d1a6e76a0edbc7d9249a8fceb5b0938c"
TARGET = "r-63c77229d1a6e76a-d026a47ed4f4b38a"
PREVIOUS = "r-0376f14868461d16-d026a47ed4f4b38a"
ROOT = Path("/var/lib/discordbot")
OUT = Path("/var/tmp/phase10-corrected-63c7722")
WORK = Path("/home/os/discordbot-phase10")
CONFIG_HASH = "14694c675aeac241f4cfd90d47c8429558f17b48d2f344f26aae6a5f57c58471"


def command(args: list[str], timeout: int = 100) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Bounded operation failed; raw output withheld")
    return result.stdout.strip()


def state(unit: str, prop: str = "ActiveState") -> str:
    return command(["systemctl", "show", unit, "-p", prop, "--value"], 10)


def source() -> None:
    sys.dont_write_bytecode = True
    sys.path.insert(0, f"/opt/discordbot/releases/{TARGET}/app/src")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guard(config: dict, actual_hash: str, marker: bool, production: str, current: str) -> None:
    if (not marker or production != "inactive" or current != PREVIOUS or actual_hash != CONFIG_HASH
            or config.get("environment") != "staging" or config.get("backup_remote") is not None
            or config.get("paths", {}).get("database") != (ROOT / "data/bot_database.db").as_posix()):
        raise ValueError("Existing reviewed synthetic installation required")


def record(stage: str, **fields) -> None:
    from discordbot.operations.adapters.filesystem import atomic_json
    path = OUT / "progress.json"
    atomic_json(path, {"stage": stage, "commit": COMMIT, "production_started": False, **fields})
    path.chmod(0o644)


async def faults() -> None:
    """Actual supervisor and probe on Pi, fake dependency, no operational DB/credential."""
    from types import SimpleNamespace
    from discordbot.composition.config import Environment, PlatformConfig, ServiceKind
    from discordbot.composition.runtime import ProcessRuntime
    from discordbot.operations.adapters.hosting import TelemetryDrain
    from discordbot.operations.adapters.probe import Probe
    from discordbot.platform.errors import DatabaseUnavailableError, ExternalTemporaryError
    from discordbot.platform.tasks import TaskSpec, RestartPolicy, RestartMode
    from discordbot.platform.telemetry import build_json_handler

    runtime = ProcessRuntime(config=PlatformConfig(ServiceKind.WATCH_WEB, Environment.TEST, TARGET))
    logger = logging.getLogger("discordbot")
    handler = build_json_handler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    drain = TelemetryDrain(runtime)
    probe = None
    try:
        await runtime.start()
        async def fail():
            raise DatabaseUnavailableError("synthetic injection")
        async def pending():
            await asyncio.sleep(30)
        attempts = 0
        async def retry():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ExternalTemporaryError("synthetic retry")
        specs = [
            (TaskSpec("fault-failed", "staging", "failed", "synthetic", 5, emit_routine_events=False), fail),
            (TaskSpec("fault-deadline", "staging", "deadline", "synthetic", .02, emit_routine_events=False), pending),
            (TaskSpec("fault-retry", "staging", "retry", "synthetic", 5,
                      restart_policy=RestartPolicy(RestartMode.ON_TRANSIENT_ERROR, 1), emit_routine_events=False), retry),
        ]
        for spec, factory in specs:
            await asyncio.gather(runtime.supervisor.start(spec, factory), return_exceptions=True)
        task = runtime.supervisor.start(TaskSpec("fault-cancel", "staging", "cancel", "synthetic", 5,
                                                emit_routine_events=False), pending)
        await asyncio.sleep(.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        async def read(*args):
            raise DatabaseUnavailableError("synthetic DB dependency")
        probe = Probe(SimpleNamespace(read=read), runtime)
        probe.schedule()
        probe.closed = True
        await probe.task
        await asyncio.sleep(0)
        events = runtime.telemetry_buffer.drain()
        names = {event.event for event in events}
        expected = {"task.failed", "task.cancelled", "task.deadline_exceeded", "task.retrying", "database.probe_failed"}
        if not expected <= names or probe.ready():
            raise ValueError("Fault diagnostics or readiness missing")
        for event in events:
            logger.info(event.event, extra={"fields": event.as_dict()})
        print(json.dumps({"events": sorted(expected), "probe_ready_after_injected_failure": probe.ready(),
                          "probe_error_codes": [event.fields["error_code"] for event in events
                                                if event.event == "database.probe_failed"]}))
    finally:
        if probe:
            await probe.stop()
        await runtime.shutdown()
        drain.flush()
        logger.removeHandler(handler)
        handler.close()


def journal_counts(since: float, until: float, units: list[str]) -> dict:
    args = ["journalctl", "--since=@" + str(since), "--until=@" + str(until), "--no-pager", "--quiet",
            "--output=json", "--output-fields=_SYSTEMD_UNIT,MESSAGE"]
    for unit in units:
        args += ["-u", unit]
    raw = command(args, 30)
    counts, events, codes = Counter(), Counter(), Counter()
    known = {"task.started", "task.succeeded", "task.failed", "task.cancelled", "task.deadline_exceeded",
             "task.retrying", "database.probe_failed"}
    tasks = {"server-maintenance", "telemetry-drain", "database-probe"}
    for line in raw.splitlines():
        row = json.loads(line)
        unit = row.get("_SYSTEMD_UNIT")
        if unit not in units:
            continue
        counts[unit] += 1
        try:
            value = json.loads(row.get("MESSAGE", ""))
        except (ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        event = value.get("event")
        if not isinstance(event, str) or event not in known:
            continue
        name = value.get("task_name")
        events[unit + ":" + event + ":" + (name if isinstance(name, str) and name in tasks else "other")] += 1
        code = value.get("error_code")
        if event == "database.probe_failed":
            allowed = {"database_unavailable", "data_integrity", "deadline_exceeded", "capacity", "conflict", "cancellation", "internal"}
            codes[code if isinstance(code, str) and code in allowed else "other"] += 1
    return {"unit_counts": dict(counts), "event_counts": dict(events), "probe_error_codes": dict(codes)}


def run() -> None:
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.build import CommandRunner
    from discordbot.operations.adapters.deployment import Services
    from discordbot.operations.adapters.filesystem import ExclusiveLock, ReleaseStore, digest, read_json
    from discordbot.operations.adapters.cli import validate_candidate

    config_path = Path("/etc/discordbot/config.json")
    store = ReleaseStore(Path("/opt/discordbot"))
    guard(read_json(config_path), digest(config_path), (ROOT / "STAGING_SYNTHETIC_ONLY").is_file(),
          state("discord-bot"), store.current())
    if store.validate(TARGET)["commit"] != COMMIT:
        raise ValueError("Prebuilt release differs")
    for unit in ("discordbot-update.timer", "discordbot-manual.timer", "discordbot-update.service", "discordbot-manual.service"):
        if state(unit) != "inactive":
            raise ValueError("Unexpected operation consumer")
    class FixtureRunner(CommandRunner):
        def run(self, args, cwd, timeout):
            return super().run(["discordbot-staging-discord" if x == "discord-bot" else x for x in args], cwd, timeout)
        def read(self, args, cwd, timeout):
            return super().read(["discordbot-staging-discord" if x == "discord-bot" else x for x in args], cwd, timeout)
    services = Services(FixtureRunner(), store.root, (9010, 9011))
    services.ready(PREVIOUS, timeout=70)
    observer = load(OUT / "observe.py", "observation")
    before = observer.sample()
    timer_active = state("discordbot-backup.timer") == "active"
    record("stopping_synthetic_pair")
    command(["systemctl", "stop", "discordbot-backup.timer"])
    limit = time.monotonic() + 180
    while state("discordbot-backup.service") in {"active", "activating", "deactivating"}:
        if time.monotonic() > limit:
            raise RuntimeError("Backup still active; no switch")
        time.sleep(1)
    with ExclusiveLock(ROOT / "operations.lock", timeout=10).acquire():
        services.stop()
        asyncio.run(validate_candidate(ROOT / "data/bot_database.db"))
        audit = Audit(ROOT / "audit")
        audit.write("staging_corrected_release", TARGET, "started", "synthetic_only")
        store.activate(TARGET)
        services.start()
        services.ready(TARGET, timeout=70)
        services.smoke(TARGET)
        audit.write("staging_corrected_release", TARGET, "ok", "synthetic_pair_ready")
    if timer_active:
        command(["systemctl", "start", "discordbot-backup.timer"])
    record("observing", release=TARGET)
    started = time.time()
    disk = shutil.disk_usage(ROOT).free
    journal_before = command(["journalctl", "--disk-usage"])
    observer.observe(OUT, 300, 10)
    (OUT / "samples.jsonl").chmod(0o644)
    (OUT / "summary.json").chmod(0o644)
    ended = time.time()
    services.smoke(TARGET)
    asyncio.run(validate_candidate(ROOT / "data/bot_database.db"))
    counts = journal_counts(started, ended, ["discordbot-staging-discord.service", "watch-web.service"])
    fault_unit = "discordbot-phase10-telemetry-fault"
    fault_started = time.time()
    command(["systemd-run", "--wait", "--collect", "--unit=" + fault_unit,
                   "-p", "User=discordbot", "-p", "Group=discordbot", "-p", "PrivateNetwork=yes",
                   "-p", "NoNewPrivileges=yes", "-p", "ProtectSystem=strict", "-p", "ProtectHome=yes",
                   "-p", "RuntimeMaxSec=30", f"/opt/discordbot/releases/{TARGET}/.venv/bin/python",
                   "-I", "-B", str(OUT / Path(__file__).name), "--fault-worker"], 45)
    fault_result = journal_counts(fault_started, time.time(), [fault_unit + ".service"])
    recorded = {key.split(":")[1] for key in fault_result["event_counts"]}
    if not {"task.failed", "task.cancelled", "task.deadline_exceeded", "task.retrying", "database.probe_failed"} <= recorded:
        raise ValueError("Fault events missing from actual journal")
    final = observer.sample()
    if state("discord-bot") != "inactive" or digest(config_path) != CONFIG_HASH:
        raise ValueError("Synthetic boundary changed")
    summary = read_json(OUT / "summary.json")
    record("complete", release=TARGET, previous=PREVIOUS, before=before, after=final,
           observation=summary, journal=counts, fault_worker=fault_result,
           journal_disk_before=journal_before, journal_disk_after=command(["journalctl", "--disk-usage"]),
           disk_free_delta=shutil.disk_usage(ROOT).free - disk,
           synthetic_database_validation="pass", staging_config_unchanged=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--fault-worker", action="store_true")
    args = parser.parse_args()
    source()
    if args.fault_worker:
        asyncio.run(faults())
        return
    if os.geteuid() != 0:
        raise ValueError("Interactive sudo required")
    if args.install:
        OUT.mkdir(mode=0o755)
        for path in (Path(__file__), WORK / "observe.py"):
            shutil.copyfile(path, OUT / path.name)
            (OUT / path.name).chmod(0o644)
        command(["systemd-run", "--collect", "--unit=discordbot-phase10-corrected-review",
                 "-p", "RuntimeMaxSec=1000", "-p", "UMask=0027",
                 f"/opt/discordbot/releases/{TARGET}/.venv/bin/python", "-I", "-B", str(OUT / Path(__file__).name)])
        print("Bounded synthetic verification started. Safe progress is recorded automatically.")
        return
    try:
        run()
    except Exception as error:
        # No blind rollback after an uncertain switch. Preserve stopped/reconciliation evidence.
        record("failed", error_type=type(error).__name__, current=Path("/opt/discordbot/current").resolve().name)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
