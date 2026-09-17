"""Explicit, encrypted-only Git backup transport. Never checks out remote files.

Runtime configuration must explicitly opt in to the approved repository/ref.
PHASE 10 validates it in an isolated manual drill before production activation.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
from tempfile import TemporaryDirectory

from discordbot.operations.adapters.filesystem import contained, read_json
from discordbot.operations.adapters.configuration import private_mode
from discordbot.platform.errors import ConflictError, DataIntegrityError, ExternalTemporaryError
from discordbot.storage.adapters.backup_codec import BACKUP_HEADER

REMOTE = "git@github.com:lgw323/Bot-Data.git"
REF = "refs/heads/db-backup"
PREFIX = "v2/backups/"
MAX_ARTIFACT = 64 * 1024 * 1024
MAX_TREE = 4096
IDENTITY = re.compile(r"[0-9]{8}T[0-9]{12}-[0-9a-f]{32}")
OID = re.compile(rb"[0-9a-f]{40}")
FIELDS = {"identity", "sha256", "key_id", "release", "schema", "timestamp"}


def checked_identity(value: str) -> str:
    if not isinstance(value, str) or not IDENTITY.fullmatch(value):
        raise DataIntegrityError("invalid timestamped backup identity")
    try:
        datetime.strptime(value.split("-")[0], "%Y%m%dT%H%M%S%f")
    except ValueError:
        raise DataIntegrityError("invalid backup time") from None
    return value


def validate_pair(payload: bytes, metadata: dict, identity: str, checksum: str) -> bytes:
    """Validate envelope shape; authentication/decrypt belongs to isolated restore."""
    checked_identity(identity)
    if (not BACKUP_HEADER or not payload.startswith(BACKUP_HEADER)
            or not len(BACKUP_HEADER) + 100 <= len(payload) <= MAX_ARTIFACT
            or hashlib.sha256(payload).hexdigest() != checksum):
        raise DataIntegrityError("encrypted artifact digest or envelope invalid")
    try:
        token = base64.b64decode(payload[len(BACKUP_HEADER):], altchars=b"-_", validate=True)
        if len(token) < 73 or token[0] != 0x80 or (len(token) - 57) % 16:
            raise ValueError
        timestamp = datetime.fromisoformat(metadata["timestamp"])
        if (set(metadata) != FIELDS or metadata["identity"] != identity
                or metadata["sha256"] != checksum or metadata["schema"] != 5
                or type(metadata["schema"]) is not int or timestamp.utcoffset() != timezone.utc.utcoffset(None)
                or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}", metadata["key_id"])
                or not re.fullmatch(r"r-[0-9a-f]{16}-[0-9a-f]{16}", metadata["release"])):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise DataIntegrityError("backup metadata not allowlisted") from None
    return (json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n").encode()


def retained(identities: set[str]) -> set[str]:
    """Latest eight plus the newest point on each of the latest seven UTC days.

    Removal affects the current v2 tree only. Git ancestors and legacy files are
    preserved, so this is a recovery selection policy, not physical erasure.
    """
    ordered = sorted((checked_identity(value) for value in identities), reverse=True)
    keep = set(ordered[:8])
    days: set[str] = set()
    for value in ordered:
        if value[:8] not in days and len(days) < 7:
            days.add(value[:8])
            keep.add(value)
    return keep


class GitTransport:
    """Repository-specific key, pinned host, no agent/config fallback or raw logs."""

    def __init__(self, key: Path, known_hosts: Path) -> None:
        if os.name != "posix":
            raise ValueError("GitHub backup transport requires Pi Linux")
        for path in (key, known_hosts):
            contained(path.parent, path)
            info = path.stat()
            if not path.is_absolute() or not path.is_file():
                raise ValueError("private SSH credential paths required")
            acl = None
            if info.st_mode & 0o077:
                try:
                    acl = os.getxattr(path, "system.posix_acl_access")
                except OSError:
                    acl = None  # private_mode rejects broad access without the exact service ACL.
            private_mode(info.st_mode, info.st_uid, os.geteuid(), acl)
        ssh = ["ssh", "-F", "/dev/null", "-i", str(key), "-o", "IdentitiesOnly=yes",
               "-o", "IdentityAgent=none", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "UserKnownHostsFile=" + str(known_hosts), "-o", "GlobalKnownHostsFile=/dev/null",
               "-o", "HostKeyAlgorithms=ssh-ed25519", "-o", "ConnectTimeout=10"]
        self.environment = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C",
                            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                            "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": shlex.join(ssh),
                            "GIT_SSH_VARIANT": "ssh", "GIT_AUTHOR_NAME": "DiscordBot Backup",
                            "GIT_AUTHOR_EMAIL": "backup@localhost", "GIT_COMMITTER_NAME": "DiscordBot Backup",
                            "GIT_COMMITTER_EMAIL": "backup@localhost"}
        self.deadline = time.monotonic() + 90

    def run(self, root: Path, arguments: list[str], data: bytes | None = None) -> bytes:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ExternalTemporaryError("backup transport total deadline exceeded")
        try:
            result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never",
                                     "-c", "protocol.ssh.allow=always", "-c", "commit.gpgsign=false", *arguments],
                                    cwd=root, input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    env=self.environment, timeout=min(30, remaining))
        except (OSError, subprocess.TimeoutExpired):
            raise ExternalTemporaryError("backup Git transport unavailable or uncertain") from None
        if result.returncode:
            raise ExternalTemporaryError("backup Git operation failed or uncertain")
        return result.stdout


class GitRemoteBackup:
    """Bounded blocking transport behind the existing async RemoteBackup port."""

    def __init__(self, settings, executor) -> None:
        self.settings, self.executor = settings, executor

    async def publish(self, artifact: Path, checksum: str, identity: str) -> None:
        def transfer() -> None:
            contained(self.settings.workspace.parent, self.settings.workspace)
            self.settings.workspace.mkdir(mode=0o700, exist_ok=True)
            transport = GitTransport(self.settings.key_file, self.settings.known_hosts_file)
            GitBackupStore(transport, self.settings.workspace).publish(artifact, checksum, identity)
        # Cancellation does not advance Backups.latest. The owner drains this
        # bounded worker before releasing its operation lock; uncertain uploads
        # require explicit readback/reconciliation, never a retry loop.
        await self.executor.run(transfer)


class GitBackupStore:
    def __init__(self, transport: GitTransport, workspace: Path) -> None:
        self.transport, self.workspace = transport, workspace

    def command(self, root: Path, *arguments: str, data: bytes | None = None) -> bytes:
        return self.transport.run(root, list(arguments), data)

    def oid(self, root: Path, *arguments: str, data: bytes | None = None) -> str:
        value = self.command(root, *arguments, data=data).strip()
        if not OID.fullmatch(value):
            raise DataIntegrityError("unexpected Git object identity")
        return value.decode("ascii")

    def fetch(self, root: Path) -> str:
        self.command(root, "init", "--bare", "--template=", "--object-format=sha1", ".")
        # Missing branch is an explicit review stop; never invent an orphan base.
        self.command(root, "fetch", "--depth=1", "--no-tags", REMOTE, REF)
        return self.oid(root, "rev-parse", "FETCH_HEAD")

    def tree(self, root: Path, commit: str) -> dict[str, str]:
        raw = self.command(root, "ls-tree", "-r", "-z", commit, "--", PREFIX)
        entries = raw.split(b"\0")[:-1]
        if len(entries) > MAX_TREE or len(raw) > 1024 * 1024:
            raise DataIntegrityError("remote backup tree exceeds limit")
        result = {}
        for entry in entries:
            try:
                header, name = entry.split(b"\t", 1)
                mode, kind, oid = header.split(b" ")
                path = name.decode("ascii")
                basename = path.removeprefix(PREFIX)
                identity, extension = basename.rsplit(".", 1)
                checked_identity(identity)
                if (mode != b"100644" or kind != b"blob" or not OID.fullmatch(oid)
                        or extension not in {"enc", "json"} or path != PREFIX + basename):
                    raise ValueError
                result[path] = oid.decode("ascii")
            except (ValueError, UnicodeError):
                raise DataIntegrityError("unexpected file in V2 backup namespace") from None
        ids = {name[len(PREFIX):].rsplit(".", 1)[0] for name in result}
        if any(PREFIX + value + suffix not in result for value in ids for suffix in (".enc", ".json")):
            raise DataIntegrityError("remote backup pair incomplete")
        return result

    def blob(self, root: Path, oid: str, maximum: int) -> bytes:
        size = self.command(root, "cat-file", "-s", oid).strip()
        if not size.isdigit() or not 0 < int(size) <= maximum:
            raise DataIntegrityError("remote blob size invalid")
        value = self.command(root, "cat-file", "blob", oid)
        if len(value) != int(size):
            raise DataIntegrityError("remote blob changed")
        return value

    def read_pair(self, root: Path, tree: dict[str, str], identity: str) -> tuple[bytes, bytes]:
        try:
            payload = self.blob(root, tree[PREFIX + identity + ".enc"], MAX_ARTIFACT)
            raw = self.blob(root, tree[PREFIX + identity + ".json"], 4096)
            record = json.loads(raw)
            return payload, validate_pair(payload, record, identity, record["sha256"])
        except (KeyError, ValueError, TypeError):
            raise DataIntegrityError("remote backup record invalid") from None

    def publish(self, artifact: Path, checksum: str, identity: str) -> dict[str, str | int]:
        checked_identity(identity)
        contained(artifact.parent, artifact)
        if artifact.name != identity + ".enc" or artifact.stat().st_size > MAX_ARTIFACT:
            raise DataIntegrityError("backup input path or size invalid")
        payload = artifact.read_bytes()
        metadata = validate_pair(payload, read_json(artifact.with_suffix(".json"), 4096), identity, checksum)
        # Temporary bare repositories are private; no remote hooks, filters or files execute.
        with TemporaryDirectory(prefix="backup-upload-", dir=self.workspace) as temporary:
            root = Path(temporary)
            previous = self.fetch(root)
            tree = self.tree(root, previous)
            ids = {name[len(PREFIX):].rsplit(".", 1)[0] for name in tree}
            for existing in ids:
                self.read_pair(root, tree, existing)
            if identity in ids:
                if self.read_pair(root, tree, identity) != (payload, metadata):
                    raise ConflictError("backup identity already has different content")
                commit = previous
            else:
                keep = retained(ids | {identity})
                if identity not in keep:
                    raise ConflictError("old input is outside the active retention window")
                self.command(root, "read-tree", previous)
                for suffix, value in ((".enc", payload), (".json", metadata)):
                    oid = self.oid(root, "hash-object", "-w", "--stdin", data=value)
                    self.command(root, "update-index", "--add", "--cacheinfo", "100644", oid, PREFIX + identity + suffix)
                for removed in ids - keep:
                    for suffix in (".enc", ".json"):
                        entry = "0 " + "0" * 40 + "\t" + PREFIX + removed + suffix + "\n"
                        self.command(root, "update-index", "--index-info", data=entry.encode("ascii"))
                new_tree = self.oid(root, "write-tree")
                commit = self.oid(root, "commit-tree", new_tree, "-p", previous, data=b"backup: publish encrypted V2 recovery point\n")
                # Single fast-forward ref update. No force, deletion, retries or history rewrite.
                self.command(root, "push", "--porcelain", REMOTE, commit + ":" + REF)
        # Independent fetch is essential: local objects do not prove remote publication.
        with TemporaryDirectory(prefix="backup-readback-", dir=self.workspace) as temporary:
            root = Path(temporary)
            observed = self.fetch(root)
            if observed != commit:
                raise ConflictError("remote head changed; publication requires reconciliation")
            tree = self.tree(root, observed)
            if self.read_pair(root, tree, identity) != (payload, metadata):
                raise DataIntegrityError("remote readback differs")
            return {"identity": identity, "sha256": checksum, "commit": commit, "active_points": len(tree) // 2}

    def download(self, identity: str, destination: Path) -> dict[str, str]:
        checked_identity(identity)
        contained(destination.parent, destination)
        if destination.exists():
            raise ConflictError("download destination must be new")
        with TemporaryDirectory(prefix="backup-download-", dir=self.workspace) as temporary:
            root = Path(temporary)
            commit = self.fetch(root)
            payload, metadata = self.read_pair(root, self.tree(root, commit), identity)
        destination.mkdir(mode=0o700)
        for suffix, value in ((".enc", payload), (".json", metadata)):
            target = destination / (identity + suffix)
            with target.open("xb") as stream:
                os.chmod(target, 0o600)
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
        return {"identity": identity, "sha256": hashlib.sha256(payload).hexdigest(), "commit": commit}
