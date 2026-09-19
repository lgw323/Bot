import configparser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "deploy" / "systemd"


@pytest.mark.parametrize("service", ["discord-bot", "watch-web"])
def test_service_contract_and_failure_isolation(service):
    text = (ASSETS / (service + ".service")).read_text()
    unit = configparser.ConfigParser(strict=False, interpolation=None)
    unit.read_string(text)
    assert unit["Service"]["User"] == "discordbot"
    assert unit["Service"]["UMask"] == "0077"
    assert unit["Service"]["Restart"] == "on-failure"
    assert int(unit["Service"]["TimeoutStopSec"]) >= 60
    assert "launch.py " + service in unit["Service"]["ExecStart"]
    assert unit["Service"]["ProtectSystem"] == "strict"
    assert unit["Service"]["StandardOutput"] == "journal"
    assert not {"requires", "bindsto", "partof"}.intersection(unit["Unit"])
    assert "EnvironmentFile" not in text and "--credentials %d" in text
    assert "LoadCredential=db_key" not in text
    assert "StartLimitBurst=3" in text


def test_timers_bound_cadence_and_never_enable_themselves():
    backup = (ASSETS / "discordbot-backup.timer").read_text()
    assert "00/4:00:00 UTC" in backup and "Persistent=true" in backup and "AccuracySec=1s" in backup
    update = (ASSETS / "discordbot-update.timer").read_text()
    assert "18:00:00 UTC" in update and "RandomizedDelaySec=30m" in update
    for file in ASSETS.glob("*.service"):
        assert "User=root" not in file.read_text()
        assert "systemctl enable" not in file.read_text()


def test_emergency_provider_pin_is_exact_and_all_normal_dependencies_are_pinned():
    lines = [line for line in (ROOT / "deploy" / "dependencies.pins").read_text().splitlines() if line and not line.startswith("#")]
    assert "yt-dlp==2026.8.19" in lines
    assert "yt-dlp-ejs==0.8.0" in lines and "deno==2.9.7" in lines
    assert all("==" in line and ">=" not in line for line in lines)
