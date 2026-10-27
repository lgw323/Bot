"""Local controller sequencing and ownership tests; no real host adapters."""
from contextlib import closing
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

import pytest

from discordbot.operations.adapters.filesystem import ExclusiveLock
from discordbot.platform.errors import ConflictError

spec = importlib.util.spec_from_file_location("cutover_fixture_model", Path(__file__).with_name("cutover_model.py"))
model_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model_module
spec.loader.exec_module(model_module)
cc, Model, sql = model_module.cc, model_module.Model, model_module.sql


@pytest.fixture
def model(tmp_path):
    return Model(tmp_path)


def intercept(model, stage, callback, *, after=False):
    real = model.controller.step
    def step(current, action, **kwargs):
        def wrapped():
            if current == stage and not after:
                callback()
            result = action()
            if current == stage and after:
                callback()
            return result
        return real(current, wrapped, **kwargs)
    model.controller.step = step


def refused():
    raise cc.Blocked("synthetic_gate")


def test_full_local_sequence_and_real_data(model):
    before = model.reader.protected(__import__('time').monotonic()+5)
    inode = model.database.stat().st_ino
    result = model.controller.run()
    assert result.status == "LOCAL_CUTOVER_PASS", result
    assert result.completed == [step.value for step in cc.Step]
    assert result.database == "verified_same_inode_wal" and result.pointer == "switched"
    assert model.database.stat().st_ino == inode and sql(model.database,"SELECT xp FROM users") == [(21,)]
    assert cc.wal.inventory(model.database)["header_mode"] == [2,2]
    assert cc.wal.inventory(model.root/"final-restored.db")["header_mode"] == [1,1]
    assert model.log.index("final_backup") < model.log.index("final_restore") < model.log.index("pointer")
    assert model.log.index("exclude") < model.log.index("stop") < model.log.index("final_backup")
    assert model.reader.protected(__import__('time').monotonic()+5) == before
    mutations = [cmd for cmd in model.runner.commands if cmd[1] in {"stop","start"}]
    assert mutations == [("systemctl","stop",*cc.PAIR),("systemctl","start",*cc.PAIR)]
    with ExclusiveLock(model.lock).acquire(): pass


def test_precutover_boundary_never_normalizes_or_stops(model):
    model.controller.plan = replace(model.plan, cutover=False, canonical_wal_approved=False)
    result = model.controller.run()
    assert result.status == "LOCAL_PRECUTOVER_PASS"
    assert result.completed == [step.value for step in list(cc.Step)[:6]]
    assert "stop" not in model.log and not (model.root/"wal.jsonl").exists()
    assert model.store.current() == model_module.PREVIOUS


@pytest.mark.parametrize("stage", list(cc.Step)[:13])
def test_every_failed_pre_pointer_gate_blocks_pointer_and_start(model, stage):
    intercept(model, stage, refused)
    result = model.controller.run()
    assert result.status == "BLOCKED" and result.stage == stage.value
    assert "pointer" not in model.log and "start" not in model.log
    assert model.store.current() == model_module.PREVIOUS
    assert sql(model.database,"SELECT xp FROM users") == [(21,)]
    if stage in list(cc.Step)[:12]:
        assert cc.Step.POINTER not in result.completed


@pytest.mark.parametrize("field,value,reason", [
    ("partial_present",True,"partial_release_requires_separate_decision"),
    ("release_count",16,"release_capacity_requires_separate_decision"),
    ("source_sha256","f"*64,"candidate_identity_or_review_changed"),
    ("manifest_sha256","f"*64,"candidate_identity_or_review_changed"),
    ("wheel_lock_sha256","f"*64,"candidate_identity_or_review_changed"),
    ("reviewed_promotion_included",False,"candidate_identity_or_review_changed"),
])
def test_partial_identity_capacity_and_review_admission(model, field, value, reason):
    original = model.workers.admission
    model.workers.admission = lambda plan: {**original(plan), field:value}
    result = model.controller.run()
    assert result.reason == reason and model.log == ["admit"]


@pytest.mark.parametrize("case", ["live", "no_wal_approval", "too_long", "infinite"])
def test_no_live_or_unapproved_invocation(model, case):
    changes = {"live":{"mode":"production"},"no_wal_approval":{"canonical_wal_approved":False},
               "too_long":{"lifetime":10801},"infinite":{"lifetime":float('inf')}}[case]
    model.controller.plan = replace(model.plan, **changes)
    result = model.controller.run()
    assert result.status == "BLOCKED" and not model.log


def test_live_exclusion_refuses_even_with_idle_sqlite_and_false_stopped_statuses(model):
    model.controller.exclusion = cc.LiveExclusion()
    with closing(sqlite3.connect(model.database)) as idle:
        result = model.controller.run()
        assert idle.execute("SELECT xp FROM users").fetchall() == [(21,)]
    assert result.reason == "live_consumer_exclusion_unavailable"
    assert "stop" not in model.log and not (model.root/"wal.jsonl").exists()


@pytest.mark.parametrize("stage", [cc.Step.FINAL_RESTORE, cc.Step.NORMALIZE, cc.Step.POINTER])
@pytest.mark.parametrize("signal", ["cancel", "connected", "healthy", "deadline"])
def test_gate_abort_has_no_later_pointer_change(model, stage, signal):
    def abort():
        if signal == "deadline":
            model.controller.work_end = model.controller.clock()-1
        else:
            setattr(model.signals, signal, signal == "cancel")
    # Use before action at a prior step's tail, so guard blocks this next step.
    prior = list(cc.Step)[list(cc.Step).index(stage)-1]
    intercept(model, prior, abort, after=True)
    result = model.controller.run()
    assert result.status == "BLOCKED" and "pointer" not in model.log and "start" not in model.log
    assert result.reason in {"cancelled","disconnected","health_abort","deadline"}


@pytest.mark.parametrize("stage", [cc.Step.NORMALIZE,cc.Step.INTENT,cc.Step.POINTER,cc.Step.START,cc.Step.READY])
def test_post_mutation_error_is_honest_and_no_automatic_rollback(model, stage):
    intercept(model, stage, refused, after=True)
    result = model.controller.run()
    assert result.status == "BLOCKED" and result.pair == "stopped"
    assert result.database in {"may_have_changed","verified_same_inode_wal"}
    assert cc.wal.inventory(model.database)["header_mode"] == [2,2]
    assert sql(model.database,"SELECT xp FROM users") == [(21,)]
    if stage in {cc.Step.POINTER,cc.Step.START,cc.Step.READY}:
        assert model.store.current() == model_module.CANDIDATE and model.log.count("pointer") == 1
        assert result.pointer in {"may_have_changed","switched"}
    else:
        assert model.store.current() == model_module.PREVIOUS and "pointer" not in model.log


def test_actual_lock_contention_before_any_step(model):
    with ExclusiveLock(model.lock).acquire():
        result = model.controller.run()
    assert result.status == "BLOCKED" and not model.log


def test_lock_remains_owned_during_failure_stop(model):
    original = model.local.stop
    checks=[]
    def stop():
        with pytest.raises(ConflictError):
            with ExclusiveLock(model.lock).acquire(): pass
        checks.append(True)
        original()
    model.local.stop=stop
    intercept(model,cc.Step.NORMALIZE,refused,after=True)
    result=model.controller.run()
    assert result.status=="BLOCKED" and checks==[True,True]
    with ExclusiveLock(model.lock).acquire(): pass


def test_fake_external_consumer_and_protected_service_change_are_refused(model):
    model.exclusion.external_consumers=1
    result=model.controller.run()
    assert result.status=="BLOCKED" and "stop" not in model.log


def test_protected_service_restart_blocks_before_cutover(model):
    def changed(): model.runner.units['supper']['NRestarts']='1'
    intercept(model,cc.Step.RETURN,changed,after=True)
    result=model.controller.run()
    assert result.reason=="protected_service_changed" and "stop" not in model.log


def test_observer_rejects_nonallowlisted_unit(model):
    with pytest.raises(cc.Blocked): model.reader.service('arbitrary; command', __import__('time').monotonic()+5)


def test_untrusted_reason_text_is_never_in_receipt(model):
    def bad(): raise cc.Blocked('SYNTHETIC_SECRET_DO_NOT_EXPORT')
    intercept(model,cc.Step.ADMIT,bad)
    result=model.controller.run()
    assert result.reason=='unexpected_gate_error'
    assert 'SYNTHETIC_SECRET' not in model.controller.receipt.read_text()


def test_existing_receipt_is_not_overwritten(model):
    model.controller.receipt.write_bytes(b'keep-existing-receipt')
    result=model.controller.run()
    assert result.status=='BLOCKED' and not model.log
    assert model.controller.receipt.read_bytes()==b'keep-existing-receipt'


def test_abort_before_stop_does_not_stop_as_cleanup(model):
    intercept(model,cc.Step.EXCLUDE,lambda:setattr(model.signals,'cancel',True),after=True)
    result=model.controller.run()
    assert result.reason=='cancelled' and 'stop' not in model.log


def test_lock_release_error_cannot_return_pass(model,monkeypatch):
    real=cc.wal.OperationOwner.__exit__
    def fail(owner,*args):
        real(owner,*args)
        raise OSError('synthetic release confirmation failure')
    monkeypatch.setattr(cc.wal.OperationOwner,'__exit__',fail)
    result=model.controller.run()
    assert result.status=='BLOCKED' and result.reason=='ownership_release_unconfirmed'


@pytest.mark.parametrize('unit',cc.OPERATIONS)
def test_operations_consumer_not_stopped_refuses_before_final_backup(model,unit):
    def started():model.runner.units[unit].update(ActiveState='active',MainPID='222')
    intercept(model,cc.Step.STOP,started,after=True)
    result=model.controller.run()
    assert result.reason=='consumer_not_stopped'
    assert 'final_backup' not in model.log and 'pointer' not in model.log


def test_stage_specific_timeout_cannot_leak_to_next_stage(model):
    fake_now=[0.0]
    model.controller.clock=lambda:fake_now[0]
    model.controller.work_end=1700
    intercept(model,cc.Step.INSTALL,lambda:fake_now.__setitem__(0,1051),after=True)
    result=model.controller.run()
    assert result.reason=='deadline' and 'preflight_fake' not in model.log


def test_three_hour_maximum_is_accepted_but_not_extended(model):
    replace(model.plan,lifetime=10800).validate()
    with pytest.raises(cc.Blocked):replace(model.plan,lifetime=10800.01).validate()


def launch(root,mode):
    worker=model_module.ROOT/'tests/support/cutover_local_worker.py'
    assert root.is_dir() and not any(root.iterdir()), 'fresh synthetic fixture required'
    token=uuid.uuid4().hex
    (root/'.cutover-test-owned').write_text(token,encoding='ascii')
    return subprocess.Popen([sys.executable,'-I','-B',str(worker),str(root),mode,token],
                            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def wait_ready(child,root):
    deadline=time.monotonic()+5
    while not (root/'ready').exists():
        assert child.poll() is None,'local model exited before ready marker'
        assert time.monotonic()<deadline,'local model ready deadline'
        time.sleep(.02)


@pytest.mark.parametrize('abort',['health','cancel','disconnect','timeout'])
def test_actual_owned_worker_abort_captures_post_normalization_state_only_reaps_owned(tmp_path,abort):
    target=tmp_path/'target';target.mkdir()
    other=tmp_path/'other';other.mkdir()
    child=launch(target,'hang-normalized')
    sentinel=launch(other,'sentinel')
    try:
        wait_ready(child,target);wait_ready(sentinel,other)
        signals=cc.Signals(cancel=abort=='cancel',connected=abort!='disconnect',healthy=abort!='health')
        started=time.monotonic()
        result=cc.supervise_owned(cc.OwnedProcess(child),target/'controller.json',signals,timeout=.2)
        (target/'supervisor-result.json').write_text(json.dumps(result,indent=2))
        assert time.monotonic()-started<3
        assert result['status']=='BLOCKED_OR_UNCERTAIN' and result['cleanup']=='owned_process_reaped'
        assert result['worker']['stage']=='normalize'
        assert result['worker']['database']=='may_have_changed'
        assert result['worker']['pointer']=='not_attempted'
        assert result['final_receipt_valid'] and not result['host_isolation_proven']
        assert child.poll() is not None and sentinel.poll() is None
        assert cc.wal.inventory(target/'synthetic.db')['header_mode']==[2,2]
        assert sql(target/'synthetic.db','SELECT xp FROM users')==[(21,)]
        with ExclusiveLock(target/'operations.lock').acquire():pass
    finally:
        cc.OwnedProcess(child).terminate_and_reap()
        cc.OwnedProcess(sentinel).terminate_and_reap()


@pytest.mark.parametrize('mode,expected',[('success','LOCAL_PASS'),('readiness-failure','BLOCKED_OR_UNCERTAIN')])
def test_actual_complete_executable_model_capture(tmp_path,mode,expected):
    child=launch(tmp_path,mode)
    try:
        result=cc.supervise_owned(cc.OwnedProcess(child),tmp_path/'controller.json',cc.Signals(),timeout=8)
        (tmp_path/'supervisor-result.json').write_text(json.dumps(result,indent=2))
        assert result['status']==expected and result['final_receipt_valid'],result
        if mode=='readiness-failure':
            assert result['worker']['pair']=='stopped' and result['worker']['pointer']=='switched'
            assert result['worker']['observed_pointer']==model_module.CANDIDATE
        assert len(json.dumps(result).encode())<8192
    finally:cc.OwnedProcess(child).terminate_and_reap()


@pytest.mark.parametrize('limit',[0,float('inf'),10800])
def test_invalid_supervisor_lifetime_still_reaps_only_supplied_child(tmp_path,limit):
    child=launch(tmp_path,'sentinel')
    try:
        wait_ready(child,tmp_path)
        with pytest.raises(cc.Blocked):
            cc.supervise_owned(cc.OwnedProcess(child),tmp_path/'controller.json',cc.Signals(),timeout=limit)
        assert child.poll() is not None
    finally:cc.OwnedProcess(child).terminate_and_reap()


def test_oversized_untrusted_result_is_not_forwarded(tmp_path):
    child=launch(tmp_path,'invalid-receipt')
    try:
        wait_ready(child,tmp_path)
        result=cc.supervise_owned(cc.OwnedProcess(child),tmp_path/'controller.json',cc.Signals(cancel=True),timeout=1)
        assert result['status']=='BLOCKED_OR_UNCERTAIN' and result['worker'] is None
        assert not result['final_receipt_valid'] and 'SYNTHETIC_UNTRUSTED_DATA' not in json.dumps(result)
    finally:cc.OwnedProcess(child).terminate_and_reap()


def test_worker_runs_in_installed_layout_without_root_conftest(tmp_path):
    """The builder exports src/tests/deploy, without source-only conftest.py."""
    app = tmp_path / 'app'
    shutil.copytree(model_module.ROOT / 'src', app / 'src',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for relative in ('deploy/tools/cutover_controller.py', 'deploy/tools/stopped_wal.py',
                     'tests/integration/operations/cutover_model.py',
                     'tests/support/cutover_local_worker.py'):
        destination = app / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(model_module.ROOT / relative, destination)
    assert not (app / 'conftest.py').exists()
    fixture = tmp_path / 'synthetic'
    fixture.mkdir()
    token = uuid.uuid4().hex
    (fixture / '.cutover-test-owned').write_text(token, encoding='ascii')
    child = subprocess.Popen(
        [sys.executable, '-I', '-B', str(app / 'tests/support/cutover_local_worker.py'),
         str(fixture), 'success', token],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        result = cc.supervise_owned(cc.OwnedProcess(child), fixture / 'controller.json',
                                    cc.Signals(), timeout=8)
        assert result['status'] == 'LOCAL_PASS' and result['final_receipt_valid'], result
    finally:
        cc.OwnedProcess(child).terminate_and_reap()
