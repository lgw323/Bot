"""Read-only full-sweep invariants. No content, credential values or recovery writes."""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess

SAFE_FAILURES={'database_integrity_or_schema','release_or_config_identity','release_schema_identity',
               'unexpected_writer','unexpected_timer','credential_scope','credential_permission',
               'explicit_resource_limit','unexpected_python_writer','media_child_capacity','public_route'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def identity(source):
    return {'manifest':digest(source.parent/'manifest.json'),
            'config':digest(Path('/etc/discordbot/config.json'))}


def check_database(path):
    from discordbot.storage.adapters.migrations import validate_ledger
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2)) as conn:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('PRAGMA trusted_schema=OFF')
        if conn.execute('PRAGMA quick_check').fetchall()!=[('ok',)] or validate_ledger(conn)!=5:
            raise RuntimeError('database_integrity_or_schema')
    return {'integrity':'ok','schema':5}


def check_credentials(credentials: Path, names: set[str], service_uid: int) -> None:
    """Apply the application's exact ACL policy without reading credential bytes."""
    from discordbot.operations.adapters.configuration import private_mode
    from discordbot.platform.errors import ConfigurationError
    if {p.name for p in credentials.iterdir()} != names:
        raise RuntimeError('credential_scope')
    try:
        if credentials.is_symlink() or not os.statvfs(credentials).f_flag & os.ST_RDONLY:
            raise RuntimeError('credential_permission')
        for path in credentials.iterdir():
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            fd = os.open(path, flags)
            try:
                info = os.fstat(fd)
                acl = None
                if info.st_mode & 0o077:
                    try:
                        acl = os.getxattr(fd, 'system.posix_acl_access')
                    except OSError:
                        acl = None  # Shared validator rejects unproven broad permissions.
                private_mode(info.st_mode, info.st_uid, service_uid, acl)
                if not os.fstatvfs(fd).f_flag & os.ST_RDONLY:
                    raise RuntimeError('credential_permission')
            finally:
                os.close(fd)
    except (OSError, ConfigurationError):
        raise RuntimeError('credential_permission') from None


def credential_service_uid(pid: int) -> int:
    import pwd
    expected = pwd.getpwnam('discordbot').pw_uid
    if (Path('/proc') / str(pid)).stat().st_uid != expected:
        raise RuntimeError('credential_permission')
    return expected


def check(source,common,value,baseline):
    if Path('/opt/discordbot/current').resolve(strict=True)!=source.parent or identity(source)!=baseline:
        raise RuntimeError('release_or_config_identity')
    result=check_database(common.ROOT/'data/bot_database.db')
    from discordbot.operations.adapters.filesystem import ReleaseStore
    manifest=ReleaseStore(Path('/opt/discordbot')).validate(source.parent.name)
    if [manifest['schema_min'],manifest['schema_max']]!=[5,5]:
        raise RuntimeError('release_schema_identity')
    for unit in ('discordbot-staging-discord.service','discordbot-backup.service',
                 'discordbot-update.service','discordbot-manual.service'):
        if common.systemd(unit)['MainPID']!='0': raise RuntimeError('unexpected_writer')
    for timer in ('backup','update','manual'):
        if common.systemd('discordbot-'+timer+'.timer')['ActiveState']!='inactive':
            raise RuntimeError('unexpected_timer')
    scopes={'discord-bot.service':{'discord_token','gemini_key','control_key'},
            'watch-web.service':{'capability_key','control_key'}}
    owners={os.getpid()}
    for unit,names in scopes.items():
        state=value['services'][unit]
        pid=int(state['MainPID']);owners.add(pid)
        credentials=Path('/proc')/str(pid)/'root/run/credentials'/unit
        check_credentials(credentials,names,credential_service_uid(pid))
        limits=subprocess.run(['systemctl','show',unit,'-p','MemoryMax','-p','TasksMax'],
                              check=True,capture_output=True,text=True,timeout=5)
        props=dict(line.split('=',1) for line in limits.stdout.splitlines())
        for cap,current in (('MemoryMax','MemoryCurrent'),('TasksMax','TasksCurrent')):
            if props[cap].isdigit() and state.get(current,'').isdigit() and int(state[current])>=int(props[cap]):
                raise RuntimeError('explicit_resource_limit')
    processes={}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            fields=dict(line.split(':',1) for line in (proc/'status').read_text().splitlines())
            processes[int(proc.name)]=(fields['Name'].strip(),int(fields['PPid']))
        except (FileNotFoundError,ProcessLookupError): continue
    def owned(pid):
        seen=set()
        while pid in processes and pid not in seen:
            if pid in owners: return True
            seen.add(pid);pid=processes[pid][1]
        return False
    if any(name.startswith(('python','pypy')) and not owned(pid) for pid,(name,_) in processes.items()):
        raise RuntimeError('unexpected_python_writer')
    if any(h.get('metrics',{}).get('music_processes',0)>2 for h in value['health'].values()):
        raise RuntimeError('media_child_capacity')
    route=subprocess.run(['/usr/bin/python3','-I','-B',str(source/'deploy/staging/review_cloudflare_route.py')],
                         check=True,capture_output=True,text=True,timeout=15)
    route=json.loads(route.stdout)
    if route.get('matching_route_count')!=1 or route.get('origin_targets')!=['http://127.0.0.1:9000'] or route.get('internal_port_route_count')!=0:
        raise RuntimeError('public_route')
    result.update(identity='verified',credential_scope='verified',writer_scope='verified',route='verified')
    return result
