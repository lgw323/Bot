"""Same-code restart fault matrix; no real services or external transports."""
import asyncio
from collections import Counter
from types import SimpleNamespace

import pytest

from discordbot.operations.application.restart import Restart


class Port:
    def __init__(self, faults=None):
        self.calls=[];self.counts=Counter();self.faults=faults or {}
        self.active=True;self.proofs=[]

    def action(self,name):
        self.calls.append(name);self.counts[name]+=1
        error=self.faults.get((name,self.counts[name]))
        if error is not None:raise error

    def preflight(self):self.action('preflight')
    def compatible(self):self.action('compatible')
    def checkpoint(self):
        self.action('checkpoint')
        proof=object();self.proofs.append(proof);return proof
    def verify_checkpoint(self,proof):
        assert proof is self.proofs[-1]
        self.action('verify')
    def stop(self):self.active=False;self.action('stop')
    def quiescent(self):assert not self.active;self.action('quiescent')
    def stop_for_recovery(self):self.active=False;self.action('recovery_stop')
    def start(self):self.active=True;self.action('start')
    def ready(self):self.action('ready')
    def smoke(self):self.action('smoke')
    def audit(self,result,reason):self.action('audit:'+result)


def fault():return OSError('PRIVATE token and path')


def test_success_has_online_and_final_stopped_verified_checkpoints():
    p=Port();outcome=Restart(p).run()
    assert outcome.result=='ok' and outcome.healthy and outcome.recovery=='not_needed'
    assert p.calls==['audit:started','preflight','compatible','checkpoint','verify','stop',
        'quiescent','compatible','checkpoint','verify','quiescent','start','ready','smoke','audit:ok']
    assert p.active and len(p.proofs)==2 and p.proofs[0] is not p.proofs[1]


@pytest.mark.parametrize('name,stage',[('audit:started','audit'),('preflight','preflight'),
    ('compatible','compatibility'),('checkpoint','backup'),('verify','backup')])
def test_failure_before_disruption_never_stops_or_starts(name,stage):
    p=Port({(name,1):fault()});result=Restart(p).run()
    assert result.result=='failed' and result.stage==stage and result.recovery=='not_needed'
    assert p.active and p.counts['stop']==p.counts['start']==p.counts['recovery_stop']==0


@pytest.mark.parametrize('name,index,stage',[('stop',1,'stop'),('quiescent',1,'checkpoint'),
    ('compatible',2,'checkpoint'),('checkpoint',2,'checkpoint'),('verify',2,'checkpoint'),
    ('quiescent',2,'checkpoint'),('start',1,'start'),('ready',1,'readiness'),('smoke',1,'smoke')])
def test_partial_stop_or_later_failure_gets_one_fresh_evidence_gated_recovery(name,index,stage):
    p=Port({(name,index):fault()});result=Restart(p).run()
    assert result.result=='failed' and result.stage==stage
    assert result.recovery=='ok' and result.healthy and p.active
    assert p.counts['stop']==1 and p.counts['recovery_stop']==1
    recovery=p.calls.index('recovery_stop')
    tail=p.calls[recovery:]
    assert tail==['recovery_stop','compatible','checkpoint','verify','quiescent','start','ready','smoke','audit:failed']
    assert p.proofs[-1] is not p.proofs[0]


@pytest.mark.parametrize('guard',[('recovery_stop',1),('compatible',2),('checkpoint',2),
    ('verify',2),('quiescent',1)])
def test_unknown_quiescence_schema_or_backup_guard_never_allows_recovery_start(guard):
    p=Port({('stop',1):fault(),guard:fault()});result=Restart(p).run()
    assert result.result=='failed' and result.recovery=='failed' and not result.healthy
    assert p.counts['start']==0 and p.counts['recovery_stop']==2 and not p.active


def test_pre_stop_success_does_not_excuse_failed_stopped_preservation_and_recovery():
    p=Port({('checkpoint',2):fault(),('checkpoint',3):fault()})
    result=Restart(p).run()
    assert len(p.proofs)==1  # Only the earlier online backup is known.
    assert p.counts['start']==0 and not p.active and result.recovery=='failed'


def test_recovery_start_failure_stops_pair_without_third_start():
    p=Port({('start',1):fault(),('start',2):fault()});result=Restart(p).run()
    assert p.counts['start']==2 and p.counts['recovery_stop']==2
    assert result.recovery=='failed' and not result.healthy and not p.active


def test_cleanup_quiescence_failure_is_explicit_and_not_forgiven():
    p=Port({('stop',1):fault(),('recovery_stop',1):fault(),('recovery_stop',2):fault()})
    result=Restart(p).run()
    assert result.recovery=='failed_stop_unconfirmed' and p.counts['start']==0


def test_failure_audit_cannot_replace_original_stage_or_stop_recovered_pair():
    p=Port({('stop',1):fault(),('audit:failed',1):fault()});result=Restart(p).run()
    assert result.stage=='stop' and result.recovery=='ok' and result.audit_failed
    assert result.healthy and p.active and p.counts['recovery_stop']==1


def test_completion_audit_failure_preserves_already_verified_healthy_pair():
    p=Port({('audit:ok',1):fault()});result=Restart(p).run()
    assert result.stage=='audit' and result.audit_failed and result.healthy
    assert p.active and p.counts['recovery_stop']==0 and p.counts['start']==1


@pytest.mark.parametrize('error',[KeyboardInterrupt(),SystemExit(7),asyncio.CancelledError()])
def test_control_exception_after_partial_stop_recovers_and_propagates_original(error):
    p=Port({('stop',1):error,('audit:failed',1):fault()});transaction=Restart(p)
    with pytest.raises(type(error)) as caught:transaction.run()
    assert caught.value is error and transaction.outcome.recovery=='ok'
    assert transaction.outcome.audit_failed and transaction.outcome.healthy and p.active


def test_control_exception_during_recovery_gets_cleanup_and_propagates():
    cancel=asyncio.CancelledError()
    p=Port({('stop',1):fault(),('checkpoint',2):cancel})
    with pytest.raises(asyncio.CancelledError) as caught:Restart(p).run()
    assert caught.value is cancel and p.counts['start']==0 and p.counts['recovery_stop']==2


def test_control_exception_before_stop_does_not_invent_cleanup_or_service_actions():
    p=Port({('preflight',1):KeyboardInterrupt()})
    with pytest.raises(KeyboardInterrupt):Restart(p).run()
    assert p.active and p.counts['stop']==p.counts['start']==p.counts['recovery_stop']==0
