"""Reviewable operational commands; explicit arguments and fail-closed defaults."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import signal
from pathlib import Path

from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.build import CommandRunner, seal_wheels
from discordbot.operations.adapters.configuration import load_settings
from discordbot.operations.adapters.deployment import LocalDeployment, Services, backup_once
from discordbot.operations.adapters.filesystem import ExclusiveLock, ReleaseStore, atomic_json, digest, read_json
from discordbot.operations.adapters.recovery import Backups, promote
from discordbot.operations.adapters.source import SourceBuilder
from discordbot.operations.adapters.retention import cleanup_releases
from discordbot.operations.adapters.manual import write_request
from discordbot.operations.adapters.operation_results import OperationResults, read_operation_result, TERMINAL
from discordbot.operations.application.deployment import Deployment
from discordbot.platform.errors import AppError, ConflictError, DataIntegrityError
from discordbot.platform.executors import BoundedExecutor
from discordbot.platform.telemetry import build_json_handler
from discordbot.storage.adapters.execution import DatabaseConfig, SqliteDatabase
from discordbot.storage.ports.contracts import DatabaseRequest, DatabaseState


async def restore(settings, audit, release, destination, candidates):
    # Missing/corrupt canonical DB does not prevent isolated recovery.
    database = SqliteDatabase(DatabaseConfig(settings.database))
    executor = BoundedExecutor(workers=1, queue_capacity=2, name="restore-files")
    try:
        return await Backups(database, settings.backups, settings.secrets.db_key, settings.key_id,
                             executor, audit).restore(destination, release, candidates=candidates)
    finally:
        await database.stop()
        await executor.close(grace_seconds=5)


async def validate_candidate(candidate):
    database = SqliteDatabase(DatabaseConfig(candidate))
    try:
        report = await database.inspect(DatabaseRequest.within(10))
        if report.state is not DatabaseState.VALID or report.migration_version != 5:
            raise DataIntegrityError("candidate failed application compatibility")
    finally:
        await database.stop()


def inspected_release(store) -> str:
    """The attempted candidate is not necessarily active after rollback."""
    try:
        return store.current() or 'none'
    except (AppError, OSError, ValueError):
        return 'unknown'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="V2 operations; production actions require reviewed operator invocation")
    parser.add_argument("command", choices=("deploy", "backup", "rehearse", "promote", "restart", "health", "manual", "cleanup", "seal-wheels"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--wheels", type=Path)
    parser.add_argument("--pins", type=Path)
    parser.add_argument("--revision", default="policy")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--candidate", action="append")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--approve-promotion", action="store_true")
    parser.add_argument("--provider-only", action="store_true")
    args = parser.parse_args(argv)
    handler = build_json_handler()
    logger = logging.getLogger("discordbot.operations")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    old_term = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    results = None
    outcome_id = None
    def publish_result(operation, source, result, stage, release, receipt=None):
        nonlocal outcome_id
        try:
            row = results.write(operation, source, result, stage, release,
                                identity=outcome_id, receipt=receipt)
            outcome_id = row['id']
        except (AppError, OSError, ValueError):
            # An optional result alert must not turn a healthy deployment into
            # rollback, or replace the operation's original failure.
            logger.warning('operation.result_persistence_failed')
    def fail_request(path, request):
        request['result'] = 'failed'
        try:
            write_request(path, request)
        except (AppError, OSError, ValueError):
            logger.warning('operation.request_acknowledgement_failed')
    try:
        if args.command == "seal-wheels":
            if not args.wheels or not args.pins:
                raise ValueError
            seal_wheels(args.wheels.absolute(), args.pins.absolute())
            return 0
        if not args.config or not args.credentials:
            raise ValueError
        settings = load_settings(args.config, args.credentials, "operations")
        store = ReleaseStore(settings.release_root)
        runner = CommandRunner()
        services = Services(runner, store.root, (settings.discord_health_port, settings.watch_health_port))
        audit = Audit(settings.audit)
        correlation = getattr(audit, 'correlation', None)
        outcome_id = correlation if isinstance(correlation, str) and re.fullmatch('[a-f0-9]{32}', correlation) else None
        results = OperationResults(settings.state)
        if args.command == "deploy":
            if not args.policy or not args.wheels:
                raise ValueError
            port = LocalDeployment(settings, SourceBuilder(store, runner, args.policy, args.wheels), services, audit)
            port.builder.provider_only = args.provider_only
            if args.provider_only:
                audit.write("provider_update", store.current() or "none", "started", "isolated_pin_change")
            publish_result('update', 'unknown', 'in_progress', 'build', inspected_release(store))
            try:
                result = Deployment(port).run(args.revision)
            except BaseException:
                publish_result('update', 'unknown', 'failed', 'unknown', inspected_release(store))
                raise
            publish_result('update', 'unknown', result.result, result.stage, inspected_release(store))
            logger.info("deployment.result", extra={"fields": {"result": result.result, "stage": result.stage, "rollback": result.rollback}})
            return 0 if result.result == "ok" else 1
        with ExclusiveLock(settings.operation_lock).acquire():
            release = store.current()
            if release is None:
                raise DataIntegrityError("a verified current release is required")
            if args.command == "backup":
                asyncio.run(backup_once(settings, audit, release))
            elif args.command == "rehearse":
                if not args.destination or not args.destination.is_absolute():
                    raise ValueError
                asyncio.run(restore(settings, audit, release, args.destination, tuple(args.candidate) if args.candidate else None))
            elif args.command == "promote":
                if not args.approve_promotion or not args.destination or not args.expected_sha256:
                    raise ValueError
                for name in services.names:
                    state = runner.read(["systemctl", "show", name, "--property=ActiveState", "--value"], store.root, 10)
                    if state not in {"inactive", "failed"}:
                        raise ConflictError("stop both services before promotion")
                candidate = args.destination.absolute()
                asyncio.run(validate_candidate(candidate))
                # Restore rehearsal is the backup evidence; promotion cannot
                # invent a fresh empty DB or hide an unvalidated candidate.
                promote(candidate, settings.database, args.expected_sha256, stopped=True, audit=audit, release=release)
            elif args.command == "health":
                services.smoke(release)
            elif args.command == "cleanup":
                audit.write("retention", release, "started", "validated_paths")
                size = cleanup_releases(store, settings.state)
                audit.write("retention", release, "ok", "complete")
                logger.info("retention.complete", extra={"fields": {"reclaimed_bytes": size}})
            elif args.command in {"restart", "manual"}:
                request = None
                if args.command == "manual":
                    path = settings.state / "manual-request.json"
                    if not path.exists():
                        return 0
                    request = read_json(path)
                    if request.get("operation") not in {"update", "restart"}:
                        raise DataIntegrityError("manual request type invalid")
                    if (not isinstance(request.get('receipt'), str)
                            or not re.fullmatch('[a-f0-9]{64}', request['receipt'])):
                        raise DataIntegrityError('manual request identity invalid')
                    if request.get('result') == 'in_progress':
                        # We hold the same kernel operation lock. A previous
                        # consumer no longer owns it; never execute its request
                        # twice after a crash or acknowledgement write failure.
                        previous = read_operation_result(settings.state)
                        if previous is not None and previous['receipt'] == request['receipt'] and previous['result'] in TERMINAL:
                            request['result'] = previous['result']
                        else:
                            publish_result(request['operation'], 'manual', 'failed', 'interrupted', release, request['receipt'])
                            request['result'] = 'failed'
                        write_request(path, request)
                        return 0 if request['result'] == 'ok' else 1
                    if request.get("result") != "pending":
                        return 0
                    request["result"] = "in_progress"
                    try:
                        write_request(path, request)
                    except BaseException:
                        publish_result(request['operation'], 'manual', 'failed', 'accepted', release, request['receipt'])
                        fail_request(path, request)
                        raise
                    if request.get("operation") == "update":
                        # Consume inside the same operation lock, and reuse the
                        # exact deployment pipeline without acquiring it twice.
                        publish_result('update', 'manual', 'in_progress', 'build', release, request['receipt'])
                        update_stage = 'build'
                        try:
                            if not args.policy or not args.wheels:
                                raise ValueError
                            from contextlib import nullcontext
                            port = LocalDeployment(settings, SourceBuilder(store, runner, args.policy, args.wheels), services, audit)
                            port.lock = nullcontext
                            update_stage = 'unknown'
                            result = Deployment(port).run("policy")
                        except BaseException:
                            publish_result('update', 'manual', 'failed', update_stage, inspected_release(store), request['receipt'])
                            fail_request(path, request)
                            raise
                        publish_result('update', 'manual', result.result, result.stage, inspected_release(store), request['receipt'])
                        request["result"] = result.result
                        write_request(path, request)
                        return 0 if result.result == "ok" else 1
                source = 'manual' if request else 'unknown'
                receipt = request['receipt'] if request else None
                publish_result('restart', source, 'in_progress', 'checkpoint', release, receipt)
                restart_stage = 'audit'
                try:
                    audit.write("restart", release, "started", "checkpoint")
                    restart_stage = 'stop'
                    services.stop()
                    restart_stage = 'backup'
                    asyncio.run(backup_once(settings, audit, release))
                    restart_stage = 'start'
                    services.start()
                    restart_stage = 'readiness'
                    services.ready(release)
                    restart_stage = 'smoke'
                    services.smoke(release)
                    restart_stage = 'audit'
                    audit.write("restart", release, "ok", "complete")
                except BaseException:
                    publish_result('restart', source, 'failed', restart_stage, release, receipt)
                    if request:
                        fail_request(settings.state / 'manual-request.json', request)
                    audit.write("restart", release, "failed", "checkpoint_backup_or_readiness")
                    raise
                publish_result('restart', source, 'ok', 'complete', release, receipt)
                if request:
                    request["result"] = "ok"
                    write_request(settings.state / "manual-request.json", request)
        return 0
    except ConflictError:
        logger.warning("operation.already_running_or_conflicting")
        return 75
    except (AppError, OSError, ValueError, KeyboardInterrupt):
        logger.error("operation.failed")
        return 1
    finally:
        signal.signal(signal.SIGTERM, old_term)
        logger.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
