"""Preserve the actual-write stopped DB via an isolated encrypted roundtrip.

This explicit Phase 10B step cannot promote, activate, start services, or publish
remotely. Its source is the reviewed current DB, never the old migration candidate.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/var/lib/discordbot')
RELEASE = Path('/opt/discordbot/releases/r-63c77229d1a6e76a-d026a47ed4f4b38a')
RUN = ROOT / 'phase10-retry-recovery-20260919-01'
OUTPUT = Path('/home/os/discordbot-phase10/retry-recovery.json')
EXPECTED = '52d2ef8813e72e0ab791d359c81a514f11622a1ca86a7165e2a211b1826cc1af'


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('isolated recovery step failed')
    return result.stdout


def write_new(path: Path, value: dict) -> None:
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def stopped() -> None:
    for name in ('discord-bot', 'watch-web', 'discordbot-staging-discord',
                 'discordbot-backup', 'discordbot-update', 'discordbot-manual'):
        unit = name + '.service'
        props = dict(line.split('=', 1) for line in checked(['systemctl', 'show', unit,
            '-p', 'ActiveState', '-p', 'MainPID']).splitlines())
        if props != {'MainPID': '0', 'ActiveState': 'inactive'}:
            raise RuntimeError('stopped services required')
    for name in ('backup', 'update', 'manual'):
        if checked(['systemctl', 'show', 'discordbot-'+name+'.timer', '-p', 'ActiveState', '--value']).strip() != 'inactive':
            raise RuntimeError('stopped timers required')


async def worker() -> None:
    from discordbot.operations.adapters.audit import Audit
    from discordbot.operations.adapters.configuration import read_secret
    from discordbot.operations.adapters.recovery import Backups
    from discordbot.platform.executors import BoundedExecutor
    from discordbot.storage.adapters.execution import SqliteDatabase, require_valid
    from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest

    key = read_secret(Path(os.environ['CREDENTIALS_DIRECTORY']), 'db_key').encode()
    key_id = json.loads(Path('/etc/discordbot/config.json').read_text())['key_id']
    database = SqliteDatabase(DatabaseConfig(RUN/'working/current.db'))
    executor = BoundedExecutor(workers=1, queue_capacity=2, name='stopped-recovery')
    backup = Backups(database, RUN/'backups', key, key_id,
                     executor, Audit(RUN/'audit'))  # Explicit local-only recovery.
    try:
        await database.start()
        before = require_valid(await database.inspect(DatabaseRequest.within(30)))
        if before.migration_version != 5:
            raise RuntimeError('schema 5 required')
        identity = await backup.create(RELEASE.name)
        target = RUN/'restored/current.db'
        await backup.restore(target, RELEASE.name, candidates=(identity,))
        restored = SqliteDatabase(DatabaseConfig(target))
        try:
            await restored.start()
            after = require_valid(await restored.inspect(DatabaseRequest.within(30)))
            fields = ('migration_version', 'data_checksum', 'metadata_checksum', 'counts')
            if any(getattr(before, key) != getattr(after, key) for key in fields):
                raise RuntimeError('restored semantics differ')
        finally:
            await restored.stop()
        write_new(RUN/'result.json', {'schema':before.migration_version, 'counts':dict(before.counts),
            'data_checksum':before.data_checksum, 'metadata_checksum':before.metadata_checksum,
            'backup_identity':identity, 'backup_sha256':digest(RUN/'backups'/(identity+'.enc')),
            'restored_sha256':digest(target), 'roundtrip':'pass', 'remote_publication':False})
    finally:
        await database.stop()
        await executor.close(grace_seconds=5)


def parent() -> int:
    import grp
    import pwd
    from discordbot.operations.adapters.filesystem import ExclusiveLock

    if OUTPUT.exists() or RUN.exists():
        raise RuntimeError('new evidence and recovery paths required')
    source = ROOT/'data/bot_database.db'
    preserved = ROOT/'phase10-precutover-63c7722/failed-attempt/data/bot_database.db'
    evidence = {'stage':'admission', 'canonical_overwritten':False, 'services_started':False}
    stage = 'admission'
    try:
        with ExclusiveLock(ROOT/'operations.lock').acquire():
            stopped()
            if Path('/opt/discordbot/current').resolve(strict=True) != RELEASE:
                raise RuntimeError('release identity differs')
            if digest(source) != EXPECTED or digest(preserved) != EXPECTED:
                raise RuntimeError('current production identity differs')
            if any(Path(str(path)+suffix).exists() for path in (source,preserved)
                   for suffix in ('-wal','-shm','-journal')):
                raise RuntimeError('unexpected sidecar; reconciliation required')
            uid = pwd.getpwnam('discordbot-deploy').pw_uid
            gid = grp.getgrnam('discordbot').gr_gid
            RUN.mkdir(mode=0o700)
            RUN.chmod(0o700)
            os.chown(RUN,uid,gid)
            for name in ('working','backups','audit','restored'):
                path = RUN/name
                path.mkdir(mode=0o700)
                os.chown(path,uid,gid)
            shutil.copyfile(source,RUN/'working/current.db')
            (RUN/'working/current.db').chmod(0o600)
            os.chown(RUN/'working/current.db',uid,gid)
            helper = RUN/Path(__file__).name
            shutil.copyfile(__file__,helper)
            helper.chmod(0o444)
            stage = 'encrypted_local_roundtrip'
            checked(['systemd-run','--wait','--pipe','--collect','--unit=discordbot-phase10-stopped-recovery',
                '-p','User=discordbot-deploy','-p','Group=discordbot','-p','UMask=0077',
                '-p','PrivateNetwork=yes','-p','ProtectSystem=strict','-p','ProtectHome=yes',
                '-p','NoNewPrivileges=yes','-p','PrivateTmp=yes','-p','RuntimeMaxSec=180',
                '-p','ReadWritePaths='+str(RUN),'-p','LoadCredential=db_key:/etc/discordbot/secrets/db_key',
                str(RELEASE/'.venv/bin/python'),'-I','-B',str(helper),'--worker'],210)
            evidence.update(json.loads((RUN/'result.json').read_text()))
            stopped()
            evidence['canonical_sha256'] = digest(source)
            evidence['preserved_sha256'] = digest(preserved)
            if evidence['canonical_sha256'] != EXPECTED or evidence['preserved_sha256'] != EXPECTED:
                raise RuntimeError('source changed during recovery')
            evidence['stage'] = 'verified_current_recovery_not_published'
    except Exception as error:
        evidence.update(stage='failed',failed_stage=stage,error_type=type(error).__name__)
    write_new(OUTPUT,evidence)
    OUTPUT.chmod(0o644)
    print('Stopped current recovery: '+evidence['stage']+'. Original DB and services unchanged.')
    return 0 if evidence['stage']=='verified_current_recovery_not_published' else 1


if __name__ == '__main__':
    if '--worker' not in sys.argv and os.geteuid() != 0:
        os.execvp('sudo',['sudo','--',str(RELEASE/'.venv/bin/python'),'-I','-B',str(Path(__file__).resolve())])
    sys.path.insert(0,str(RELEASE/'app/src'))
    if sys.argv[1:] == ['--worker']:
        asyncio.run(worker())
    elif sys.argv[1:]:
        raise SystemExit('unexpected arguments')
    else:
        raise SystemExit(parent())
