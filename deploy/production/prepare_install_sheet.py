"""Prepare an isolated, exact 10B config; never install it or activate production."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

OUT = Path('/var/lib/discordbot/phase10-install-plan-63c7722')
SOURCE = Path('/etc/discordbot/production-candidate')
CONFIG_SHA = '5f1f360a6be8d23e4217051902605f0360651cf72d8926efc10caf851557e3f3'
CANDIDATE = Path('/var/lib/discordbot/phase10-recovery-20260916-01/restored/candidate.db')
DB_SHA = '8d17018f1927d91b9ea633700471a6cda7388633b175a560be36f4b904ae4e5b'
REMOTE = {'kind': 'git-ssh', 'repository': 'git@github.com:lgw323/Bot-Data.git', 'ref': 'refs/heads/db-backup'}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_private(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or not info.st_size:
        raise ValueError('Credential source ownership/type/mode invalid')


def prepare(value: dict, config_sha: str, db_sha: str) -> dict:
    if config_sha != CONFIG_SHA or db_sha != DB_SHA:
        raise ValueError('Reviewed source identity changed')
    if value.get('environment') != 'production' or value.get('backup_remote') is not None:
        raise ValueError('Unexpected candidate configuration')
    return dict(value, backup_remote=dict(REMOTE))


def main() -> None:
    import grp

    if os.geteuid() != 0:
        raise ValueError('Interactive sudo required')
    value = prepare(json.loads((SOURCE / 'config.json').read_text()), digest(SOURCE / 'config.json'), digest(CANDIDATE))
    for name in ('discord_token', 'gemini_key', 'control_key', 'capability_key', 'db_key'):
        check_private(SOURCE / 'secrets' / name)
    for name in ('id_ed25519', 'known_hosts'):
        check_private(Path('/etc/discordbot/backup-ssh-candidate') / name)
    OUT.mkdir(mode=0o750)
    os.chown(OUT, 0, grp.getgrnam('discordbot').gr_gid)
    path = OUT / 'config.json'
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.chown(path, 0, grp.getgrnam('discordbot').gr_gid)
    result = {'stage': 'prepared_not_installed', 'source_config_sha256': CONFIG_SHA,
              'install_config_sha256': digest(path), 'candidate_sha256': DB_SHA,
              'config_path': str(path), 'credential_source_permissions': 'pass',
              'production_activated': False}
    report = OUT / 'result.json'
    report.write_text(json.dumps(result, sort_keys=True) + '\n')
    report.chmod(0o644)
    # Only this metadata copy is public; config and credentials stay private.
    public = Path('/var/tmp/phase10-install-sheet-result.json')
    fd = os.open(public, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(fd, 'w') as stream:
        json.dump(result, stream, sort_keys=True)
    print('Isolated install sheet prepared. Production configuration is unchanged.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Preparation stopped: ' + type(error).__name__ + '; no production installation performed.')
        raise SystemExit(1) from None
