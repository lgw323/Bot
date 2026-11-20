"""Real isolated SQLite checkpoints and quiescence, never production paths."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from cryptography.fernet import Fernet
import pytest

from discordbot.operations.adapters import restart as module
from discordbot.operations.adapters.audit import Audit
from discordbot.operations.adapters.deployment import Services
from discordbot.operations.adapters.filesystem import atomic_json, digest, read_json
from discordbot.operations.adapters.restart import LocalRestart
from discordbot.operations.application.restart import Restart
from discordbot.operations.ports.restart import RestartCleanupUnconfirmed
from discordbot.platform.errors import DataIntegrityError, ExternalTemporaryError
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest


@pytest.fixture
def local(tmp_path):
    for name in ['data','state','cache','backups','audit']:(tmp_path/name).mkdir()
    path=tmp_path/'data'/'synthetic.db'
    async def bootstrap():
        database=SqliteDatabase(DatabaseConfig(path))
        try:await DataRecovery(database).bootstrap(DatabaseRequest.within(5))
        finally:await database.stop()
    asyncio.run(bootstrap())
    active={'release':'release','schema_max':5}
    store=SimpleNamespace(current=lambda:active['release'],
        validate=lambda _:dict(schema_min=5,schema_max=active['schema_max']))
    services=SimpleNamespace(names=('discord-bot','watch-web'),ready=Mock(),smoke=Mock(),stop=Mock(),
        start=Mock(),stop_for_rollback=Mock(),_rollback_state=Mock(),quiescence=SimpleNamespace(verify=Mock()))
    settings=SimpleNamespace(database=path,state=tmp_path/'state',cache=tmp_path/'cache',backups=tmp_path/'backups',audit=tmp_path/'audit',
        secrets=SimpleNamespace(db_key=Fernet.generate_key()),key_id='synthetic-key',backup_remote=object())
    port=LocalRestart(settings,store,services,Audit(settings.audit),'release')
    return SimpleNamespace(port=port,active=active,services=services,settings=settings,tmp=tmp_path,root=settings.backups/'restart-local')


def test_fresh_local_checkpoint_is_independently_restored_and_hash_pinned(local,monkeypatch):
    h=local;real=module.Backups;remotes=[]
    def construct(*args,**kwargs):remotes.append(kwargs['remote']);return real(*args,**kwargs)
    monkeypatch.setattr(module,'Backups',construct)
    before=digest(h.settings.database)
    h.port.preflight();h.port.compatible()
    proof=h.port.checkpoint();h.port.verify_checkpoint(proof)
    assert remotes==[None,None]  # Configured remote is deliberately not used.
    assert proof.archive_sha256==digest(h.root/(proof.identity+'.enc'))
    assert proof.metadata_sha256==digest(h.root/(proof.identity+'.json'))
    assert digest(h.settings.database)==before
    assert not list(h.root.glob('.rehearsal-*'))
    h.services.start.assert_not_called()


def test_local_checkpoints_never_advance_or_prune_canonical_remote_backup_evidence(local):
    h=local;root=h.settings.backups
    atomic_json(root/'latest.json',{'identity':'old-remote-checkpoint'})
    (root/'old-remote-checkpoint.enc').write_bytes(b'synthetic canonical encrypted object')
    atomic_json(root/'old-remote-checkpoint.json',{'identity':'old-remote-checkpoint','timestamp':'old'})
    (root/'remote-work').mkdir();(root/'remote-work'/'marker').write_bytes(b'synthetic remote workspace')
    before={p.relative_to(root):digest(p) for p in root.rglob('*') if p.is_file()}
    proof=h.port.checkpoint();h.port.verify_checkpoint(proof)
    assert h.root!=root and (h.root/'latest.json').is_file()
    assert read_json(root/'latest.json')=={'identity':'old-remote-checkpoint'}
    assert all((root/name).is_file() and digest(root/name)==value for name,value in before.items())
    records=[read_json(p) for p in h.settings.audit.glob('*.json')]
    assert records and {row['operation'] for row in records}=={'restart_checkpoint'}


def test_private_checkpoint_root_cannot_be_an_existing_regular_file(local):
    h=local;h.root.write_bytes(b'unexpected file')
    with pytest.raises(DataIntegrityError):h.port.checkpoint()
    assert h.root.read_bytes()==b'unexpected file'
    h.services.stop.assert_not_called();h.services.start.assert_not_called()


@pytest.mark.parametrize('kind',['archive','metadata','wrong_release','wrong_key','wrong_schema','cipher'])
def test_corrupt_or_incompatible_proof_never_touches_live_database(local,kind):
    h=local;proof=h.port.checkpoint();before=digest(h.settings.database)
    archive=h.root/(proof.identity+'.enc');metadata=h.root/(proof.identity+'.json')
    if kind=='archive':archive.write_bytes(b'corrupt')
    elif kind=='metadata':metadata.write_text('{',encoding='utf-8')
    else:
        record=read_json(metadata)
        if kind=='wrong_release':record['release']='other-release'
        elif kind=='wrong_key':record['key_id']='other-key'
        elif kind=='wrong_schema':record['schema']=99
        else:
            archive.write_bytes(b'corrupt')
            record['sha256']=digest(archive)
            proof=replace(proof,archive_sha256=record['sha256'])
        atomic_json(metadata,record);proof=replace(proof,metadata_sha256=digest(metadata))
    with pytest.raises(DataIntegrityError):h.port.verify_checkpoint(proof)
    assert digest(h.settings.database)==before
    h.services.start.assert_not_called()


def test_backup_changed_during_isolated_validation_is_rejected(local,monkeypatch):
    h=local;proof=h.port.checkpoint();real=module.Backups._validated_candidate
    @asynccontextmanager
    async def altered(self,*args):
        async with real(self,*args) as candidate:yield candidate
        (h.root/(proof.identity+'.enc')).write_bytes(b'changed after validation')
    monkeypatch.setattr(module.Backups,'_validated_candidate',altered)
    with pytest.raises(DataIntegrityError):h.port.verify_checkpoint(proof)
    h.services.start.assert_not_called()


@pytest.mark.parametrize('method',['preflight','compatible','checkpoint','start','stop','quiescent','stop_for_recovery','ready','smoke'])
def test_release_pointer_change_blocks_every_service_or_data_stage(local,method):
    h=local;h.active['release']='unexpected'
    with pytest.raises(DataIntegrityError):getattr(h.port,method)()
    for name in ['start','stop','stop_for_rollback','ready','smoke']:getattr(h.services,name).assert_not_called()


def test_schema_incompatibility_blocks_restart(local):
    h=local;h.active['schema_max']=4
    with pytest.raises(DataIntegrityError):h.port.compatible()
    h.services.start.assert_not_called()


def test_read_only_persistence_guard_fails_before_any_service_action(local,monkeypatch):
    h=local;original=module.os.access
    monkeypatch.setattr(module.os,'access',lambda path,mode:False if path==h.settings.backups else original(path,mode))
    with pytest.raises(DataIntegrityError):h.port.preflight()
    for name in ['start','stop','stop_for_rollback','ready','smoke']:getattr(h.services,name).assert_not_called()


def test_missing_or_corrupt_database_is_never_bootstrapped_by_restart(local):
    h=local;h.settings.database.write_bytes(b'not a database')
    with pytest.raises(DataIntegrityError):h.port.compatible()
    assert h.settings.database.read_bytes()==b'not a database'


@pytest.mark.parametrize('closer',['database','executor','both'])
def test_primary_checkpoint_failure_and_unknown_owned_cleanup_blocks_all_recovery_evidence_and_start(local,monkeypatch,closer):
    h=local;created=[];closed=[];failed=[False];primary=OSError('PRIVATE original backup error')
    class Database:
        def __init__(self,*args):created.append('database')
        async def inspect(self,*args):return SimpleNamespace(state=module.DatabaseState.VALID,migration_version=5)
        async def start(self):pass
        async def stop(self):
            closed.append('database')
            if failed[0] and closer in {'database','both'}:raise OSError('PRIVATE database close')
    class Executor:
        def __init__(self,*args,**kwargs):created.append('executor')
        async def close(self,**kwargs):
            closed.append('executor')
            if failed[0] and closer in {'executor','both'}:raise OSError('PRIVATE executor close')
    class Backups:
        def __init__(self,*args,**kwargs):pass
        async def create(self,*args):failed[0]=True;raise primary
    def install_after_stop():
        monkeypatch.setattr(module,'SqliteDatabase',Database)
        monkeypatch.setattr(module,'BoundedExecutor',Executor)
        monkeypatch.setattr(module,'Backups',Backups)
    h.services.stop.side_effect=install_after_stop
    result=Restart(h.port).run()
    assert result.stage=='checkpoint' and result.recovery=='failed_stop_unconfirmed'
    assert result.recovery_stage=='owned_cleanup' and not result.healthy
    assert h.port.cleanup_unknown and created==['database','database','executor']
    assert closed[-2:]==['database','executor']  # Both close attempts, even if first fails.
    assert h.services.stop_for_rollback.call_count==2
    h.services.start.assert_not_called()
    before=list(created)
    for action in [h.port.compatible,h.port.checkpoint,h.port.start]:
        with pytest.raises(RestartCleanupUnconfirmed):action()
    assert created==before


def test_inspection_primary_error_is_preserved_when_its_worker_close_also_fails(local,monkeypatch):
    h=local;primary=OSError('PRIVATE inspect failure');created=[]
    class Database:
        def __init__(self,*args):created.append('database')
        async def inspect(self,*args):raise primary
        async def stop(self):raise OSError('PRIVATE close failure')
    monkeypatch.setattr(module,'SqliteDatabase',Database)
    with pytest.raises(OSError) as caught:h.port.compatible()
    assert caught.value is primary and h.port.cleanup_unknown
    with pytest.raises(RestartCleanupUnconfirmed):h.port.checkpoint()
    with pytest.raises(RestartCleanupUnconfirmed):h.port.start()
    assert created==['database']
    h.services.start.assert_not_called()


def test_successful_inspection_with_failed_close_latches_unknown(local,monkeypatch):
    h=local
    class Database:
        def __init__(self,*args):pass
        async def inspect(self,*args):return SimpleNamespace(state=module.DatabaseState.VALID,migration_version=5)
        async def stop(self):raise OSError('PRIVATE close failure')
    monkeypatch.setattr(module,'SqliteDatabase',Database)
    with pytest.raises(RestartCleanupUnconfirmed):h.port.compatible()
    assert h.port.cleanup_unknown


@pytest.mark.parametrize('evidence',['empty','descendant','unknown'])
def test_real_services_failed_stop_recovery_requires_actual_recursive_absence(local,evidence):
    h=local;root=h.tmp/'cgroup';root.mkdir();(root/'cgroup.controllers').write_text('')
    parent=root/'system.slice';parent.mkdir()
    for name in ['discord-bot','watch-web']:
        node=parent/(name+'.service');node.mkdir();(node/'cgroup.procs').write_text('')
    if evidence=='descendant':
        node=parent/'watch-web.service'/'child';node.mkdir();(node/'cgroup.procs').write_text('123\n')
    elif evidence=='unknown':(root/'cgroup.controllers').unlink()
    class Runner:
        def run(self,args,cwd,timeout):raise ExternalTemporaryError('fixed failed stop')
        def read(self,args,cwd,timeout):
            return '\n'.join(['LoadState=loaded','ActiveState=failed','MainPID=0','ControlGroup='])
    services=Services(Runner(),h.tmp,(9010,9011),cgroup_root=root)
    h.port.services=services
    with pytest.raises(ExternalTemporaryError):h.port.stop()  # Strict forward rule unchanged.
    if evidence=='empty':h.port.stop_for_recovery();h.port.quiescent()
    else:
        with pytest.raises(ExternalTemporaryError):h.port.stop_for_recovery()
