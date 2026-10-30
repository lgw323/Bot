"""CLI outcome evidence comes from fake completed operations, never live services."""
import hashlib
from types import SimpleNamespace

import pytest

from discordbot.operations.adapters import cli
from discordbot.operations.adapters.filesystem import read_json
from discordbot.operations.adapters.manual import write_request
from discordbot.operations.adapters.operation_notifications import result_message
from discordbot.operations.adapters.operation_results import OperationResults, read_operation_result
from discordbot.operations.ports.deployment import Outcome


@pytest.fixture
def harness(tmp_path, monkeypatch):
    state = tmp_path / 'state';state.mkdir()
    calls = []
    failures = {'stage': None}
    active = {'value': 'old-release'}
    settings = SimpleNamespace(state=state, release_root=tmp_path, operation_lock=tmp_path / 'operation.lock',
        audit=tmp_path / 'audit', discord_health_port=9010, watch_health_port=9011)
    class Audit:
        def write(self, operation, release, result, reason):
            calls.append('audit:' + result)
            if failures['stage'] == 'audit' and result == 'started':
                raise OSError('PRIVATE audit path')
    def action(stage):
        def run(*args):
            calls.append(stage)
            if failures['stage'] == stage:raise OSError('PRIVATE token and error details')
        return run
    services = SimpleNamespace(stop=action('stop'), start=action('start'), ready=action('readiness'),
        smoke=action('smoke'), names=('discord-bot', 'watch-web'))
    async def backup(*args):action('backup')()
    monkeypatch.setattr(cli, 'load_settings', lambda *args: settings)
    monkeypatch.setattr(cli, 'ReleaseStore', lambda *args: SimpleNamespace(root=tmp_path, current=lambda: active['value']))
    monkeypatch.setattr(cli, 'CommandRunner', lambda: None)
    monkeypatch.setattr(cli, 'Services', lambda *args: services)
    monkeypatch.setattr(cli, 'Audit', lambda *args: Audit())
    monkeypatch.setattr(cli, 'backup_once', backup)
    monkeypatch.setattr(cli, 'SourceBuilder', lambda *args: SimpleNamespace(provider_only=False))
    monkeypatch.setattr(cli, 'LocalDeployment', lambda *args: SimpleNamespace(builder=args[1], lock=None))
    result = {'value': Outcome('new-release', 'ok', 'complete')}
    def deploy(*args):
        calls.append('deployment')
        if failures['stage'] == 'deployment':raise OSError('PRIVATE build stderr')
        if result['value'].result in {'ok','ok_cleanup_failed'}:
            active['value'] = result['value'].release
        return result['value']
    monkeypatch.setattr(cli, 'Deployment', lambda *args: SimpleNamespace(run=deploy))
    common = ['--config', str(tmp_path / 'not-a-real-config'), '--credentials', str(tmp_path / 'no-credentials-read')]
    return SimpleNamespace(state=state, calls=calls, failures=failures, result=result, common=common,
        manual=state / 'manual-request.json')


def pending(h, operation='restart', result='pending'):
    row = {'operation': operation, 'receipt': hashlib.sha256(b'isolated-request').hexdigest(), 'result': result, 'history': []}
    write_request(h.manual, row)
    return row


def test_restart_success_published_only_after_ready_smoke_and_audit(harness, monkeypatch):
    h = harness;published=[];original = OperationResults.write
    def write(self, *args, **kwargs):
        published.append((args[2], list(h.calls)))
        return original(self, *args, **kwargs)
    monkeypatch.setattr(OperationResults, 'write', write)
    assert cli.main(['restart', *h.common]) == 0
    assert [x[0] for x in published] == ['in_progress', 'ok']
    assert published[0][1] == []
    assert published[-1][1] == ['audit:started', 'stop', 'backup', 'start', 'readiness', 'smoke', 'audit:ok']
    assert read_operation_result(h.state)['result'] == 'ok'


@pytest.mark.parametrize('stage', ['audit','stop','backup','start','readiness','smoke'])
def test_each_restart_failure_is_terminal_and_never_success(harness, stage, capsys):
    h=harness;pending(h);h.failures['stage']=stage
    assert cli.main(['manual', *h.common]) == 1
    assert read_json(h.manual)['result'] == 'failed'
    row = read_operation_result(h.state)
    assert row['result'] == 'failed' and row['stage'] == stage
    assert 'PRIVATE' not in capsys.readouterr().err
    assert 'private' not in (h.state / 'operation-result.json').read_text().lower()


def test_manual_update_missing_flags_does_not_leave_in_progress(harness):
    h=harness;pending(h, 'update')
    assert cli.main(['manual', *h.common]) == 1
    assert read_json(h.manual)['result'] == 'failed'
    assert read_operation_result(h.state)['stage'] == 'build'
    assert h.calls == []


def test_manual_update_builder_failure_is_terminal(harness, monkeypatch):
    h=harness;pending(h,'update')
    def fail(*args):raise OSError('PRIVATE policy')
    monkeypatch.setattr(cli,'SourceBuilder',fail)
    assert cli.main(['manual', *h.common, '--policy','synthetic-policy','--wheels','synthetic-wheels']) == 1
    assert read_json(h.manual)['result'] == 'failed' and read_operation_result(h.state)['result'] == 'failed'
    assert h.calls == []


def test_unchanged_update_does_not_claim_service_health_or_restart(harness):
    h=harness;pending(h,'update');h.result['value']=Outcome('old-release','ok','unchanged')
    assert cli.main(['manual', *h.common, '--policy','synthetic-policy','--wheels','synthetic-wheels']) == 0
    row=read_operation_result(h.state);title,text,_=result_message(row)
    assert row['release']=='old-release' and '변경 없음' in title and '실행하지 않았습니다' in text
    assert h.calls == ['deployment']


def test_automatic_deploy_source_unknown_and_actual_result_release_used(harness):
    h=harness
    assert cli.main(['deploy', *h.common, '--policy','synthetic-policy','--wheels','synthetic-wheels']) == 0
    row=read_operation_result(h.state)
    assert row['source']=='unknown' and row['release']=='new-release' and row['result']=='ok'
    h.result['value']=Outcome('failed-candidate','failed','smoke','ok')
    assert cli.main(['deploy', *h.common, '--policy','synthetic-policy','--wheels','synthetic-wheels']) == 1
    assert read_operation_result(h.state)['release']=='new-release'


def test_cleanup_warning_preserves_existing_cli_exit_and_truthful_status(harness):
    h=harness;h.result['value']=Outcome('new-release','ok_cleanup_failed','retention')
    assert cli.main(['deploy', *h.common, '--policy','synthetic-policy','--wheels','synthetic-wheels']) == 1
    row=read_operation_result(h.state)
    assert row['result']=='ok_cleanup_failed' and row['stage']=='retention'
    assert '정리 확인 필요' in result_message(row)[0]


def test_orphaned_in_progress_request_not_executed_twice(harness):
    h=harness;pending(h,result='in_progress')
    assert cli.main(['manual', *h.common]) == 1
    assert h.calls==[] and read_json(h.manual)['result']=='failed'
    assert read_operation_result(h.state)['stage']=='interrupted'


def test_known_completed_outcome_reconciles_request_ack_without_service_action(harness):
    h=harness;row=pending(h,result='in_progress')
    recorded=OperationResults(h.state).write('restart','manual','ok','complete','old-release',receipt=row['receipt'])
    assert cli.main(['manual', *h.common]) == 0
    assert h.calls==[] and read_json(h.manual)['result']=='ok'
    assert read_operation_result(h.state)==recorded


def test_initial_request_ack_write_failure_records_failed_and_clears_owned_running(harness, monkeypatch):
    h=harness;pending(h);original=cli.write_request;once=[True]
    def fail(path,value):
        original(path,value)
        if value['result']=='in_progress' and once[0]:once[0]=False;raise OSError('PRIVATE metadata')
    monkeypatch.setattr(cli,'write_request',fail)
    assert cli.main(['manual',*h.common])==1
    assert read_json(h.manual)['result']=='failed' and read_operation_result(h.state)['stage']=='accepted'
    assert h.calls==[]


def test_success_ack_failure_does_not_destroy_verified_outcome_or_repeat_restart(harness, monkeypatch):
    h=harness;pending(h);original=cli.write_request;once=[True]
    def fail(path,value):
        if value['result']=='ok' and once[0]:once[0]=False;raise OSError('PRIVATE ack failure')
        original(path,value)
    monkeypatch.setattr(cli,'write_request',fail)
    assert cli.main(['manual',*h.common])==1
    assert read_json(h.manual)['result']=='in_progress' and read_operation_result(h.state)['result']=='ok'
    calls=list(h.calls)
    assert cli.main(['manual',*h.common])==0
    assert read_json(h.manual)['result']=='ok' and h.calls==calls


def test_optional_outcome_write_failure_never_rolls_back_healthy_restart(harness, monkeypatch, capsys):
    h=harness;original=OperationResults.write
    def fail(self,*args,**kwargs):
        if args[2]=='ok':raise PermissionError('PRIVATE path token')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(OperationResults,'write',fail)
    assert cli.main(['restart',*h.common])==0
    assert h.calls==['audit:started','stop','backup','start','readiness','smoke','audit:ok']
    assert read_operation_result(h.state)['result']=='in_progress'
    assert 'PRIVATE' not in capsys.readouterr().err
