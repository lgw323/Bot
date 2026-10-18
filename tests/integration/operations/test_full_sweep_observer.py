"""Only explicit full-sweep policy tolerates functional failures; hard gates remain."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from discordbot.composition.live_validation import full_sweep_active
from .test_music_smoke_observer import observer

RELEASE='r-'+'a'*16+'-'+'b'*16


def healthy():
    return {'services':{name:{'ActiveState':'active','MainPID':'123','Result':'success','NRestarts':'0'}
                       for name in ('discord-bot.service','watch-web.service')},
            'health':{str(port):{'ready':True,'release':RELEASE} for port in (9010,9011)}}


@pytest.mark.parametrize('event',[
    {'event':'summary.request','result':'external_temporary','http_status':503},
    {'event':'summary.request','result':'external_temporary','http_status':429},
    {'event':'music.work_failed','stage':'prepare','error_code':'external_permanent'},
    {'event':'music.work_failed','stage':'tts','error_code':'external_temporary'},
    {'event':'music.ui_failed','stage':'action','error_code':'internal'},
])
def test_functional_failure_keeps_healthy_pair_for_independent_watch(event):
    m=observer();diag={'recent_stages':[event]}
    hard,soft=m.full_sweep_failures(diag)
    assert hard is None and soft==[event]
    assert m.health_trigger(healthy(),healthy(),RELEASE,0) is None
    # Original strict observer keeps its legacy Summary/Music stop policy.
    if event['event']!='music.ui_failed': assert m.failure_trigger([event])


@pytest.mark.parametrize('code',['data_integrity','database_unavailable'])
def test_integrity_error_is_hard_even_when_recent_tail_has_only_provider_failure(code):
    m=observer()
    assert m.full_sweep_failures({'error_codes':{code:1},'recent_stages':[]})[0]==code


@pytest.mark.parametrize('mutation,trigger',[
    ('restart','service_crash_or_restart'),('crash','service_crash_or_restart'),
    ('release','release_mismatch'),('readiness','persistent_readiness_loss')])
def test_runtime_safety_still_stops(mutation,trigger):
    m=observer();value=healthy();bad=0
    if mutation=='restart': value['services']['discord-bot.service']['NRestarts']='1'
    if mutation=='crash': value['services']['discord-bot.service']['ActiveState']='failed'
    if mutation=='release': value['health']['9010']['release']='different'
    if mutation=='readiness': bad=3
    assert m.health_trigger(value,healthy(),RELEASE,bad)==trigger


def test_failure_classification_never_invokes_subprocess_or_network(monkeypatch):
    m=observer()
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k: pytest.fail('unexpected process or request'))
    for _ in range(5):
        hard,soft=m.full_sweep_failures({'recent_stages':[{'event':'summary.request','result':'external_temporary','http_status':503}]})
        assert hard is None and soft
    assert m.full_sweep_failures({'event_counts':{'task.retrying':1}})[0]=='automatic_retry_during_sweep'


@pytest.mark.parametrize('change',[None,'expired','future','unbounded','release','mode','malformed'])
def test_full_sweep_admission_is_finite_exact_and_explicit(tmp_path,change,monkeypatch):
    import discordbot.composition.live_validation as marker
    path=tmp_path/'marker'
    value={'mode':'phase10-full-sweep','release':RELEASE,'started_unix':100,'expires_unix':200}
    if change=='expired': value['expires_unix']=140
    if change=='future': value['started_unix']=160
    if change=='unbounded': value['expires_unix']=9999
    if change=='release': value['release']='different'
    if change=='mode': value['mode']='ordinary'
    path.write_text('legacy' if change=='malformed' else json.dumps(value));path.chmod(0o600)
    # Mock privileged POSIX ownership, never create a privileged production marker.
    monkeypatch.setattr(marker.os,'fstat',lambda _:SimpleNamespace(st_uid=0,st_mode=0o100600,st_size=path.stat().st_size))
    assert full_sweep_active(RELEASE,path,now=150)==(change is None)


def test_marker_rejects_nonroot_or_writable_metadata(tmp_path,monkeypatch):
    import discordbot.composition.live_validation as marker
    path=tmp_path/'marker';path.write_text('{}')
    for uid,mode in ((1000,0o100600),(0,0o100666)):
        monkeypatch.setattr(marker.os,'fstat',lambda _:SimpleNamespace(st_uid=uid,st_mode=mode,st_size=2))
        assert not full_sweep_active(RELEASE,path,now=150)


def test_schema_readonly_hard_gate_uses_synthetic_db(tmp_path):
    import sqlite3
    from discordbot.storage.adapters.schema import create_legacy_schema
    from discordbot.storage.adapters.migrations import apply_pending
    path=Path(__file__).resolve().parents[3]/'deploy/production/sweep-safety.py'
    spec=importlib.util.spec_from_file_location('sweep_safety_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    db=tmp_path/'synthetic.db'
    with sqlite3.connect(db) as conn:
        create_legacy_schema(conn);conn.commit()
    with pytest.raises(RuntimeError): m.check_database(db)
    with sqlite3.connect(db) as conn: apply_pending(conn,lambda:None)
    assert m.check_database(db)=={'integrity':'ok','schema':5}
    db.write_bytes(b'synthetic corruption')
    with pytest.raises(sqlite3.DatabaseError): m.check_database(db)


def test_schema_failure_closes_observer_database_connection(tmp_path,monkeypatch):
    import sqlite3
    path=Path(__file__).resolve().parents[3]/'deploy/production/sweep-safety.py'
    spec=importlib.util.spec_from_file_location('sweep_close_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    closed=[]
    class Connection(sqlite3.Connection):
        def close(self):
            closed.append(True);super().close()
    connect=sqlite3.connect
    db=tmp_path/'synthetic.db';connect(db).close()
    monkeypatch.setattr(m.sqlite3,'connect',lambda *a,**k:connect(*a,**k,factory=Connection))
    with pytest.raises(RuntimeError): m.check_database(db)
    assert closed==[True]


def test_handoff_requires_every_gate_and_human_confirmation(tmp_path):
    m=observer();control=tmp_path
    state=SimpleNamespace(systemd=lambda _: {'ActiveState':'active','MainPID':'999','NRestarts':'0'})
    data={'release':RELEASE,'gates':{g:'PASS' for g in m.SWEEP_GATES},
          'human_audio_confirmed':True,'chrome_confirmed':True,
          'replacement_guard':'phase10-retry-'+RELEASE[2:18]+'-post-cutover-test.service'}
    path=control/'all-gates-pass.json';path.write_text(json.dumps(data))
    assert m.handoff_ready(control,RELEASE,state,[])
    assert not m.handoff_ready(control,RELEASE,state,[{'event':'summary.request'}])
    data['gates']['summary']='FAIL';path.write_text(json.dumps(data))
    assert not m.handoff_ready(control,RELEASE,state,[])


def test_full_observation_continues_across_summary_music_tts_then_stops_at_deadline(tmp_path,monkeypatch):
    m=observer();clock=[0.];samples=[];stops=[];written=[]
    events=[{'event':'summary.request','result':'external_temporary','http_status':503},
            {'event':'music.work_failed','stage':'prepare','error_code':'external_permanent'},
            {'event':'music.work_failed','stage':'tts','error_code':'external_temporary'}]
    monkeypatch.setattr(m.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(m.time,'sleep',lambda _:clock.__setitem__(0,clock[0]+5))
    monkeypatch.setattr(m,'diagnostics',lambda _: {'recent_stages':events[:min(3,int(clock[0]/5)+1)]})
    monkeypatch.setattr(m,'preserve_failure',lambda *a:stops.append(clock[0]) or {'pair_stopped':True})
    def sample():
        samples.append(clock[0]);return healthy()
    common=SimpleNamespace(METRICS=set(),sample=sample,write_json=lambda path,data:written.append(data))
    safety=SimpleNamespace(identity=lambda _: {},check=lambda *a:{'schema':5},SAFE_FAILURES=set())
    args=SimpleNamespace(policy='full-sweep',since_unix=1,release=RELEASE,seconds=12)
    m.observe_loop(args,tmp_path,tmp_path,tmp_path/'preserved',common,safety,lambda _:True)
    assert samples==[0,5,10,15] and stops==[15]
    assert written[-1]['soft_failures']==events
    assert written[-1]['last']['guard_trigger']=='sweep_finished_or_deadline'
    assert written[-1]['last']['health']['9011']['ready']  # Watch remained available throughout.
