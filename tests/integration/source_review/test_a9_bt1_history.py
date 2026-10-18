"""Mandatory source-history controls; never installed admission or runtime fallback."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from discordbot.operations.adapters import backup_destination as policy
from discordbot.operations.adapters import git_backup
from discordbot.platform.errors import ConfigurationError

ROOT = Path(__file__).resolve().parents[3]
HEAD = "cb54da9948370db64133a0ead6c9df89d0b61055"
REPOSITORY = "git@github.com:lgw323/A9-V1-Reviewer-Synthetic.git"
ISOLATED = {"kind": "git-ssh", "target": "isolated", "repository": REPOSITORY,
            "ref": "refs/heads/db-backup"}


def forbidden(*args, **kwargs):
    pytest.fail("review boundary reached credentials, executor or real transport")


def test_prechange_rejection_and_routing(tmp_path, monkeypatch):
    """Fresh negative control from exact HEAD source, never replacing live modules."""
    relative = "src/discordbot/operations/adapters/configuration.py"
    old = subprocess.check_output(["git", "show", HEAD + ":" + relative], cwd=ROOT)
    # Reverse-patched entry export was independently matched to this HEAD text.
    assert hashlib.sha256(old.replace(b"\r\n", b"\n")).hexdigest() == (
        "641e7698097cce5e7d6e75e92df752fe9e89257ebaa2f31455d95dfab05d5a73")
    path = tmp_path / "baseline_configuration.py"
    path.write_bytes(old)
    name = "_a9_v1_baseline_configuration"
    spec = importlib.util.spec_from_file_location(name, path)
    baseline = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, baseline)
    spec.loader.exec_module(baseline)
    value = json.loads((ROOT / "deploy/config.example.json").read_text())
    value["paths"] = {key: str(tmp_path / key) for key in value["paths"]}
    value["backup_remote"] = ISOLATED
    file = tmp_path / "config.json"
    file.write_text(json.dumps(value))
    monkeypatch.setattr(baseline, "read_secret", forbidden)
    monkeypatch.setattr(git_backup, "GitTransport", forbidden)
    with pytest.raises(ConfigurationError, match="unapproved remote backup configuration"):
        baseline.load_settings(file, tmp_path, "operations")
    calls = []
    def record(root, arguments, data=None):
        calls.append(arguments)
        return b"a" * 40 if arguments[0] == "rev-parse" else b""
    old_store_source = subprocess.check_output(
        ["git", "show", HEAD + ":src/discordbot/operations/adapters/git_backup.py"], cwd=ROOT)
    old_store_path = tmp_path / "baseline_git_backup.py"
    old_store_path.write_bytes(old_store_source)
    old_spec = importlib.util.spec_from_file_location("_a9_v1_baseline_git_backup", old_store_path)
    old_module = importlib.util.module_from_spec(old_spec)
    old_spec.loader.exec_module(old_module)
    old_module.GitBackupStore(SimpleNamespace(run=record), tmp_path).fetch(tmp_path)
    assert calls[1] == ["fetch", "--depth=1", "--no-tags", policy.REMOTE, policy.REF]
