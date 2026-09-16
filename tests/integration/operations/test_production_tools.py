import importlib.util
from pathlib import Path

import pytest

from .test_production_configuration import production_config
from .test_runtime import config_files


def tool(relative):
    path = Path(__file__).resolve().parents[3] / "deploy" / relative
    spec = importlib.util.spec_from_file_location("production_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_refuses_unrelated_credential_before_loading(config_files, monkeypatch):
    file, credentials = config_files
    preflight = tool("production/preflight.py")
    monkeypatch.setattr("discordbot.operations.adapters.configuration.load_settings", lambda *_: pytest.fail("secrets read"))
    with pytest.raises(ValueError, match="scope"):
        preflight.check(file, credentials, "discord-bot", False)


def test_preflight_uses_only_scoped_files_and_does_not_start_application(config_files, tmp_path):
    file, credentials = config_files
    production_config(file, credentials)
    preflight = tool("production/preflight.py")
    scoped = tmp_path / "scoped"
    scoped.mkdir(mode=0o700)
    for name in preflight.SCOPES["discord-bot"]:
        (scoped / name).write_bytes((credentials / name).read_bytes())
        (scoped / name).chmod(0o600)
    result = preflight.check(file, scoped, "discord-bot", False)
    assert result["scope"] == "exact"
    assert result["database_open"] == result["network_login"] == "not_attempted"
    with pytest.raises(ValueError, match="mount"):
        preflight.check(file, scoped, "discord-bot", True)


def test_hidden_input_rejects_placeholder_and_malformed_keys():
    entry = tool("production/enter_secret.py")
    for name, value in (("db_key", "not-a-key"), ("discord_token", "censored"),
                        ("gemini_key", "two words"), ("control_key", "short")):
        with pytest.raises(ValueError):
            entry.validate(name, value)
