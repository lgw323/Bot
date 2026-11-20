"""Pinned local restart evidence. No network backup or release-pointer writes."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat

from discordbot.operations.adapters.filesystem import contained, digest, identifier, read_json, sync_dir
from discordbot.operations.adapters.recovery import Backups
from discordbot.operations.ports.restart import RestartCleanupUnconfirmed
from discordbot.platform.errors import DataIntegrityError
from discordbot.platform.executors import BoundedExecutor
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest, DatabaseState


@dataclass(frozen=True, slots=True)
class Checkpoint:
    identity: str
    archive_sha256: str
    metadata_sha256: str


class LocalRestart:
    def __init__(self, settings, store, services, audit, release: str) -> None:
        self.settings, self.store, self.services, self.journal = settings, store, services, audit
        self.release = identifier(release)
        self.cleanup_unknown = False

    def _require_owned_cleanup(self) -> None:
        if self.cleanup_unknown:
            raise RestartCleanupUnconfirmed('restart owned worker cleanup is unconfirmed')

    def _checkpoint_root(self, *, create: bool = False) -> Path:
        # Never advance the canonical remote-backup latest/RPO marker or prune
        # its recovery points merely because a local restart needed evidence.
        root = contained(self.settings.backups, self.settings.backups/'restart-local')
        try:
            info = root.lstat()
        except FileNotFoundError:
            if not create:
                raise DataIntegrityError('restart checkpoint directory missing') from None
            root.mkdir(mode=0o700)
            sync_dir(root.parent)
            info = root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or os.name == 'posix'
                and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700)):
            raise DataIntegrityError('restart checkpoint directory invalid')
        return root

    def _manifest(self):
        if self.store.current() != self.release:
            raise DataIntegrityError('restart release changed')
        return self.store.validate(self.release)

    def preflight(self) -> None:
        self._require_owned_cleanup()
        self._manifest()
        for path in (self.settings.database.parent, self.settings.state, self.settings.cache,
                     self.settings.backups, self.settings.audit):
            if not path.is_dir() or not os.access(path, os.W_OK):
                raise DataIntegrityError('restart persistence preflight failed')
        self.services.ready(self.release)
        self.services.smoke(self.release)

    def compatible(self) -> None:
        self._require_owned_cleanup()
        manifest = self._manifest()
        async def check():
            database = SqliteDatabase(DatabaseConfig(self.settings.database))
            primary = None
            try:
                report = await database.inspect(DatabaseRequest.within(10))
                if (report.state is not DatabaseState.VALID
                        or not manifest['schema_min'] <= report.migration_version <= manifest['schema_max']):
                    raise DataIntegrityError('restart database incompatible')
            except BaseException as error:
                primary = error
                raise
            finally:
                try:
                    await database.stop()
                except BaseException as error:
                    self.cleanup_unknown = True
                    if primary is None:
                        if not isinstance(error, Exception):
                            raise
                        raise RestartCleanupUnconfirmed('restart database worker cleanup is unconfirmed') from None
        asyncio.run(check())

    @asynccontextmanager
    async def _backup_tools(self, *, start: bool):
        self._require_owned_cleanup()
        database = SqliteDatabase(DatabaseConfig(self.settings.database))
        executor = BoundedExecutor(workers=1, queue_capacity=2, name='restart-local-backup')
        primary = None
        try:
            if start:
                await database.start()
            root = self._checkpoint_root(create=start)
            journal = self.journal
            class CheckpointAudit:
                def write(self, operation, release, result, reason):
                    if operation != 'backup':
                        raise DataIntegrityError('restart checkpoint audit invalid')
                    journal.write('restart_checkpoint', release, result, reason)
            yield Backups(database, root, self.settings.secrets.db_key,
                          self.settings.key_id, executor, CheckpointAudit(), remote=None)
        except BaseException as error:
            primary = error
            raise
        finally:
            errors = []
            for close in (database.stop, lambda: executor.close(grace_seconds=5)):
                try:
                    await close()
                except BaseException as error:
                    errors.append(error)
                    self.cleanup_unknown = True
            if errors and primary is None:
                control = next((error for error in errors if not isinstance(error, Exception)), None)
                if control is not None:
                    raise control
                raise RestartCleanupUnconfirmed('restart backup worker cleanup is unconfirmed') from None

    def _files(self, proof: Checkpoint) -> tuple[Path, Path]:
        if (type(proof) is not Checkpoint or type(proof.identity) is not str
                or any(type(v) is not str or re.fullmatch('[a-f0-9]{64}', v) is None
                       for v in (proof.archive_sha256, proof.metadata_sha256))):
            raise DataIntegrityError('restart checkpoint proof invalid')
        identifier(proof.identity)
        root = self._checkpoint_root()
        archive, metadata = (contained(root, root/(proof.identity+suffix)) for suffix in ('.enc', '.json'))
        for path, maximum in ((archive, 64*1024*1024+4096), (metadata, 65536)):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
                raise DataIntegrityError('restart checkpoint file invalid')
        return archive, metadata

    def checkpoint(self) -> Checkpoint:
        self._require_owned_cleanup()
        self._manifest()
        async def create():
            async with self._backup_tools(start=True) as backups:
                identity = await backups.create(self.release)
                root = self._checkpoint_root()
                # The returned proof pins exact immutable artifacts, not latest.
                return Checkpoint(identity, digest(contained(root, root/(identity+'.enc'))),
                                  digest(contained(root, root/(identity+'.json'))))
        return asyncio.run(create())

    def verify_checkpoint(self, proof: object) -> None:
        self._require_owned_cleanup()
        self._manifest()
        archive, metadata = self._files(proof)
        def verify_hashes():
            record = read_json(metadata, 65536, reject_duplicates=True)
            if (digest(archive) != proof.archive_sha256 or digest(metadata) != proof.metadata_sha256
                    or record.get('identity') != proof.identity or record.get('release') != self.release
                    or record.get('schema') != 5 or record.get('key_id') != self.settings.key_id
                    or record.get('sha256') != proof.archive_sha256):
                raise DataIntegrityError('restart checkpoint changed')
        verify_hashes()
        async def validate():
            async with self._backup_tools(start=False) as backups:
                # Isolated decrypt/restore + application validation; never promote.
                async with backups._validated_candidate(proof.identity, self._checkpoint_root()):
                    pass
        asyncio.run(validate())
        self._files(proof); verify_hashes()

    def stop(self) -> None:
        self._manifest(); self.services.stop()

    def quiescent(self) -> None:
        self._manifest()
        for name in self.services.names:
            self.services._rollback_state(name)
            self.services.quiescence.verify(name+'.service')
        for name in self.services.names:
            self.services._rollback_state(name)

    def stop_for_recovery(self) -> None:
        self._manifest(); self.services.stop_for_rollback()

    def start(self) -> None:
        self._require_owned_cleanup()
        self._manifest(); self.services.start()

    def ready(self) -> None:
        self._manifest(); self.services.ready(self.release)

    def smoke(self) -> None:
        self._manifest(); self.services.smoke(self.release)

    def audit(self, result: str, reason: str) -> None:
        self.journal.write('restart', self.release, result, reason)
