import base64
import json
from pathlib import Path
import warnings

import pytest

from .test_production_tools import tool


def test_wizard_collects_ordered_hidden_inputs_and_generates_independent_watch_keys(monkeypatch, capsys):
    setup = tool("production/setup-production.py")
    template = json.loads((Path(__file__).resolve().parents[3] / "deploy/production/config.template.json").read_text())
    key = base64.urlsafe_b64encode(b"s" * 32).decode()
    hidden = iter(("synthetic-token", "mismatch", "synthetic-token", "synthetic-token",
                   "synthetic-gemini", "synthetic-gemini", key, key))
    visible = iter(("not-an-id", "1", "100001", "100002", "100003", "100004", "100005", ""))
    monkeypatch.setattr(setup.getpass, "getpass", lambda _: next(hidden))
    monkeypatch.setattr("builtins.input", lambda _: next(visible))
    config, values = setup.collect(template)
    setup.validate_config(config)
    assert config["main_channels"] == [[100002, 100003]]
    assert config["music_channels"] == [[100002, 100004]]
    assert config["public_origin"] == "https://watch.lgw323.com"
    assert values["control_key"] != values["capability_key"]
    assert len(values["control_key"]) >= 32 and len(values["capability_key"]) >= 32
    output = capsys.readouterr().out
    assert all(value not in output for value in values.values())
    broken = dict(config, master="REPLACE_WITH_ID")
    with pytest.raises(ValueError):
        setup.validate_config(broken)


def test_wizard_refuses_getpass_echo_fallback(monkeypatch):
    setup = tool("production/setup-production.py")
    def unsafe(_):
        warnings.warn("echo unavailable", setup.getpass.GetPassWarning)
        pytest.fail("Must not fall back to echoed input")
    monkeypatch.setattr(setup.getpass, "getpass", unsafe)
    with pytest.raises(setup.getpass.GetPassWarning):
        setup.ask_secret("discord_token", "test")


def test_wizard_validates_before_creating_any_candidate(tmp_path):
    setup = tool("production/setup-production.py")
    target = tmp_path / "candidate"
    with pytest.raises(ValueError):
        setup.persist(target, {}, {}, owner=0, group=0)
    assert not target.exists()


def test_wizard_refuses_noninteractive_launch_without_prompting(monkeypatch, capsys):
    setup = tool("production/setup-production.py")
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(setup.getpass, "getpass", lambda _: pytest.fail("secret prompt"))
    assert setup.main() == 1
    assert "SSH" in capsys.readouterr().out
