"""Only safe diagnostic fields cross the privileged live-smoke observer."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def observer():
    path = Path(__file__).resolve().parents[3]/'deploy/production/observe-smoke.py'
    spec = importlib.util.spec_from_file_location('music_smoke_observer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_observer_retains_cause_but_drops_vendor_content_and_unbounded_exit(monkeypatch):
    module = observer()
    events = [
        {'event':'music.work_failed','stage':'prepare','error_code':'external_permanent',
         'reason':'http_forbidden','child_exit_code':1,'message':'private payload','url':'private url'},
        {'event':'music.smoke_failed','stage':'live_smoke','result':'failed',
         'reason':'private title','child_exit_code':123456789},
    ]
    raw = '\n'.join(json.dumps({'PRIORITY':'4','MESSAGE':json.dumps(event)}) for event in events)
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=raw, returncode=0))
    result = module.diagnostics(1)
    assert result['recent_stages'][0]['reason'] == 'http_forbidden'
    assert result['recent_stages'][0]['child_exit_code'] == 1
    assert result['recent_stages'][1] == {'event':'music.smoke_failed','stage':'live_smoke','result':'failed'}
    assert 'private' not in json.dumps(result) and '123456789' not in json.dumps(result)
