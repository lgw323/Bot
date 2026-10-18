"""Exercise current SourceBuilder against a disposable local Git repository."""
import os
from pathlib import Path
import subprocess

import pytest

from discordbot.operations.adapters.filesystem import atomic_json
from discordbot.operations.adapters.source import SourceBuilder
from tests.integration.operations.test_build import Runner, builder


@pytest.mark.parametrize("selection", ["explicit", "policy"])
def test_source_export_build_publish_uses_exact_scoped_revision(builder, selection):
    repository = builder.source
    for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
        (repository / name).write_text("# synthetic metadata\n")
    (repository / "tests" / "test_synthetic.py").write_text("def test_local(): assert True\n")
    (repository / ".env").write_text("SYNTHETIC_NOT_A_CREDENTIAL=excluded\n")
    (repository / "data").mkdir()
    (repository / "data" / "excluded.txt").write_text("synthetic outside source scope")
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                       GIT_AUTHOR_NAME="Synthetic", GIT_AUTHOR_EMAIL="synthetic@localhost",
                       GIT_COMMITTER_NAME="Synthetic", GIT_COMMITTER_EMAIL="synthetic@localhost")

    def git(*arguments):
        return subprocess.check_output(["git", "-c", "core.hooksPath=" + os.devnull, *arguments],
                                       cwd=repository, env=environment, stderr=subprocess.DEVNULL, timeout=10)
    git("init", "--template=", ".")
    git("add", "--", "src", "tests", "deploy", "pyproject.toml", "requirements.txt", "requirements-dev.txt", ".env", "data")
    git("commit", "-m", "synthetic source fixture")
    commit = git("rev-parse", "HEAD").decode().strip()

    class LocalRunner(Runner):
        def run(self, args, cwd, timeout):
            if args[:2] == ["git", "archive"]:
                self.calls.append(args)
                assert cwd == repository
                assert args[4] == commit
                git(*args[1:])
            elif args[:2] == ["git", "fetch"]:
                self.calls.append(args)
                assert args == ["git", "fetch", "--no-tags", "origin", "refs/heads/reviewed"]
                # Network is the only substituted source boundary.
            else:
                super().run(args, cwd, timeout)

        def read(self, args, cwd, timeout):
            assert args == ["git", "rev-parse", "--verify", "FETCH_HEAD^{commit}"]
            assert selection == "policy" and cwd == repository
            return commit

    policy = repository.parent / "policy.json"
    atomic_json(policy, {"repository": str(repository), "ref": "refs/heads/reviewed"})
    runner = LocalRunner()
    source = SourceBuilder(builder.store, runner, policy, builder.wheels)
    identity = source.build("policy" if selection == "policy" else commit)
    source.publish(identity)
    manifest = source.store.validate(identity)
    assert manifest["commit"] == commit
    assert "app/src/app.py" in manifest["files"]
    assert "app/tests/test_synthetic.py" in manifest["files"]
    assert not (source.store.path(identity) / "app" / ".env").exists()
    assert not (source.store.path(identity) / "app" / "data").exists()
    assert not list((source.store.root / "candidates").iterdir())
    assert source.store.current() is None
    assert sum(command[:2] == ["git", "fetch"] for command in runner.calls) == (selection == "policy")
