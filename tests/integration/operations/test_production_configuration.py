import json

import pytest

from discordbot.operations.adapters.configuration import load_settings
from discordbot.platform.errors import ConfigurationError
from .test_runtime import config_files


def production_config(file, credentials):
    value = json.loads(file.read_text())
    value.update(environment="production", master=12345678901234567, admin_channel=12345678901234568,
                 main_channels=[[12345678901234569, 12345678901234570]],
                 music_channels=[[12345678901234569, 12345678901234571]],
                 public_origin="https://watch.example.org", key_id="production-key-1")
    (credentials / "discord_token").write_text("test-format-only-not-a-live-token")
    (credentials / "gemini_key").write_text("test-format-only-not-a-live-key")
    file.write_text(json.dumps(value))
    return value


@pytest.mark.parametrize("field,bad", [("master", 1), ("public_origin", "https://watch.example.invalid"),
                                      ("key_id", "staging-key-1"), ("gemini_model", "REPLACE_WITH_MODEL")])
def test_production_placeholders_fail_before_secret_access(config_files, monkeypatch, field, bad):
    file, credentials = config_files
    value = production_config(file, credentials)
    value[field] = bad
    file.write_text(json.dumps(value))
    monkeypatch.setattr("discordbot.operations.adapters.configuration.read_secret", lambda *_: pytest.fail("secret accessed"))
    with pytest.raises(ConfigurationError):
        load_settings(file, credentials, "discord-bot")


def test_structurally_complete_configuration_and_secret_placeholder(config_files):
    file, credentials = config_files
    production_config(file, credentials)
    assert load_settings(file, credentials, "discord-bot").environment == "production"
    (credentials / "discord_token").write_text("censored")
    with pytest.raises(ConfigurationError):
        load_settings(file, credentials, "discord-bot")


def test_shipped_staging_config_stays_usable(config_files):
    file, credentials = config_files
    assert load_settings(file, credentials, "watch-web").environment == "staging"
