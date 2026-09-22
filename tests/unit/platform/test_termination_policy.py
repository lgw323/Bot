from pathlib import Path

import pytest

from discordbot.platform.termination import TerminationPolicy


def test_production_policy_agrees_with_both_service_templates():
    policy = TerminationPolicy()
    assert (policy.startup, policy.grace, policy.loop, policy.kill, policy.reap) == (60, 20, 40, 70, 90)
    root = Path(__file__).resolve().parents[3]
    for name in ('discord-bot', 'watch-web'):
        unit = (root / 'deploy/systemd' / (name + '.service')).read_text()
        assert f'TimeoutStopSec={int(policy.reap)}\n' in unit
        assert 'KillMode=control-group' in unit and 'deploy/launch.py' in unit


@pytest.mark.parametrize('values', [(1, 1, 3), (0, .1, 1), (1, float('nan'), 1), (1, .1, float('inf'))])
def test_invalid_termination_hierarchy_is_rejected(values):
    with pytest.raises(ValueError):
        TerminationPolicy(*values)


def test_public_entrypoint_always_selects_guardian(monkeypatch):
    from discordbot.composition import main
    calls = []
    monkeypatch.setattr(main, 'load_settings', lambda *_: pytest.fail('guardian loaded credentials'))
    def supervise(command):
        calls.append(command(42))
        return 7
    monkeypatch.setattr(main, 'supervise', supervise)
    assert main.main(['watch-web', '--config', 'synthetic']) == 7
    assert len(calls) == 1 and '42' in calls[0]
    assert 'discordbot.composition.worker' in calls[0][4]
