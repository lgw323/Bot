"""Explicit candidate policy and bounded export; never mutate a running checkout."""

import re
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from discordbot.operations.adapters.build import Builder
from discordbot.operations.adapters.filesystem import contained, read_json
from discordbot.platform.errors import DataIntegrityError


class SourceBuilder(Builder):
    def __init__(self, store, runner, policy: Path, wheels: Path):
        super().__init__(store, runner, store.root / "candidates", wheels)
        self.policy = policy

    def build(self, revision: str) -> str:
        policy = read_json(self.policy, 8192)
        if set(policy) != {"repository", "ref"} or not re.fullmatch(r"refs/heads/[a-zA-Z0-9/_-]+", policy["ref"]):
            raise DataIntegrityError("invalid update policy")
        repository = Path(policy["repository"])
        if not repository.is_absolute() or not repository.is_dir():
            raise DataIntegrityError("candidate repository unavailable")
        if revision == "policy":
            self.runner.run(["git", "fetch", "--no-tags", "origin", policy["ref"]], repository, 120)
            commit = self.runner.read(["git", "rev-parse", "--verify", "FETCH_HEAD^{commit}"], repository, 10)
        else:
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                raise DataIntegrityError("explicit full revision required")
            commit = revision
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise DataIntegrityError("candidate commit invalid")
        parent = self.store.root / "candidates"
        parent.mkdir(exist_ok=True)
        candidate = contained(parent, parent / uuid4().hex)
        candidate.mkdir()
        archive = candidate / "source.zip"
        try:
            self.runner.run(["git", "archive", "--format=zip", "--output=" + str(archive), commit,
                             "src", "tests", "deploy", "pyproject.toml", "requirements.txt", "requirements-dev.txt"], repository, 60)
            with zipfile.ZipFile(archive) as package:
                items = package.infolist()
                if len(items) > 10000 or sum(i.file_size for i in items) > 64 * 1024 * 1024:
                    raise DataIntegrityError("source export exceeds bound")
                for item in items:
                    target = contained(candidate, candidate / item.filename)
                    if (item.external_attr >> 16) & 0o170000 == 0o120000:
                        raise DataIntegrityError("source links are forbidden")
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with package.open(item) as source, target.open("xb") as output:
                            shutil.copyfileobj(source, output, 1024 * 1024)
            self.source = candidate
            return super().build(commit)
        finally:
            contained(parent, candidate)
            shutil.rmtree(candidate)
