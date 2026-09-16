"""Explicit once-only production file configuration; no dotenv or ambient aliases."""

from __future__ import annotations

import base64
import os
import stat
import struct
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from discordbot.operations.adapters.filesystem import contained, read_json
from discordbot.platform.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class Secrets:
    discord_token: str = field(default="", repr=False)
    gemini_key: str = field(default="", repr=False)
    db_key: bytes = field(default=b"", repr=False)
    control_key: str = field(default="", repr=False)
    capability_key: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class Settings:
    service: str
    environment: str
    database: Path = field(repr=False)
    state: Path = field(repr=False)
    cache: Path = field(repr=False)
    backups: Path = field(repr=False)
    audit: Path = field(repr=False)
    release_root: Path = field(repr=False)
    operation_lock: Path = field(repr=False)
    master: int = field(repr=False)
    admin_channel: int = field(repr=False)
    main_channels: tuple[tuple[int, int], ...] = field(repr=False)
    music_channels: tuple[tuple[int, int], ...] = field(repr=False)
    public_origin: str = field(repr=False)
    public_port: int
    control_port: int
    discord_health_port: int
    watch_health_port: int
    gemini_model: str
    key_id: str
    limits: tuple[tuple[str, int], ...]
    secrets: Secrets = field(repr=False)


def placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("replace_with", "replace_me", "censored", "your_", "changeme", "placeholder"))


def private_mode(mode: int, owner: int, permitted_owner: int, acl: bytes | None = None) -> None:
    if not stat.S_ISREG(mode) or owner not in {0, permitted_owner}:
        raise ConfigurationError("secret file ownership or permissions invalid")
    if not mode & 0o077:
        return
    # systemd 255 uses root:root 0440 with a named-service-user ACL. The mode's
    # group bits represent the ACL mask, not actual owning-group access. Accept
    # only this exact read-only shape; broad groups/other users remain forbidden.
    undefined = 0xFFFFFFFF
    expected = [(1, 4, undefined), (2, 4, permitted_owner), (4, 0, undefined),
                (16, 4, undefined), (32, 0, undefined)]
    if (owner != 0 or stat.S_IMODE(mode) != 0o440 or acl is None or len(acl) != 44
            or acl[:4] != struct.pack("<I", 2)
            or list(struct.iter_unpack("<HHI", acl[4:])) != expected):
        raise ConfigurationError("secret file ACL permits unexpected access")


def read_secret(root: Path, name: str) -> str:
    try:
        path = contained(root, root / name)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if os.name != "nt":
                acl = None
                if info.st_mode & 0o077 and hasattr(os, "getxattr"):
                    try:
                        # Inspect the already opened descriptor; no path race or
                        # credential content is needed for this metadata check.
                        acl = os.getxattr(stream.fileno(), "system.posix_acl_access")
                    except OSError:
                        acl = None  # private_mode rejects broad access without proof.
                private_mode(info.st_mode, info.st_uid, os.geteuid(), acl)
            value = stream.read(4097).decode().strip()
        if not value or len(value) > 4096 or any(c.isspace() for c in value):
            raise ValueError
        return value
    except (OSError, ValueError, UnicodeError):
        raise ConfigurationError("required secret missing or invalid") from None


def load_settings(path: Path, credentials: Path, service: str) -> Settings:
    try:
        value = read_json(path, 65536)
        expected = {"version", "environment", "paths", "master", "admin_channel", "main_channels", "music_channels",
                    "public_origin", "ports", "gemini_model", "key_id", "limits", "backup_remote"}
        if set(value) != expected or value["version"] != 1 or value["environment"] not in {"staging", "production"}:
            raise ValueError
        if service not in {"discord-bot", "watch-web", "operations"}:
            raise ValueError
        # A remote destination requires an explicitly installed adapter. Refuse
        # a silently ignored destination or fallback to the public code remote.
        if value["backup_remote"] is not None:
            raise ConfigurationError("remote backup adapter must be explicitly configured")
        paths = value["paths"]
        if set(paths) != {"database", "state", "cache", "backups", "audit", "release_root", "operation_lock"}:
            raise ValueError
        parsed = {key: Path(raw) for key, raw in paths.items()}
        if any(not p.is_absolute() for p in parsed.values()) or len(set(parsed.values())) != len(parsed):
            raise ValueError
        if path.is_relative_to(parsed["release_root"]) or credentials.is_relative_to(parsed["release_root"]):
            raise ValueError
        for key, p in parsed.items():
            contained(p.parent, p)
            if key != "release_root" and p.is_relative_to(parsed["release_root"]):
                raise ValueError
        if any(type(value[key]) is not int or not 0 < value[key] < 2**63 for key in ("master", "admin_channel")):
            raise ValueError
        channels = {}
        for key in ("main_channels", "music_channels"):
            pairs = tuple(tuple(pair) for pair in value[key])
            if (not 1 <= len(pairs) <= 4 or any(len(pair) != 2 for pair in pairs)
                    or any(type(x) is not int or not 0 < x < 2**63 for pair in pairs for x in pair)
                    or len(dict(pairs)) != len(pairs)):
                raise ValueError
            channels[key] = pairs
        origin = urlsplit(value["public_origin"])
        if origin.port is not None and not 1 <= origin.port <= 65535:
            raise ValueError
        if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
                or origin.path or origin.query or origin.fragment):
            raise ValueError
        ports = value["ports"]
        if set(ports) != {"public", "control", "discord_health", "watch_health"}:
            raise ValueError
        if len(set(ports.values())) != 4 or any(type(p) is not int or not 1024 <= p <= 65535 for p in ports.values()):
            raise ValueError
        allowed = {"task_capacity", "telemetry_queue_capacity", "metrics_series_capacity", "executor_workers", "executor_queue_capacity"}
        if not set(value["limits"]).issubset(allowed):
            raise ValueError
        ceilings = {"task_capacity": (1, 256), "telemetry_queue_capacity": (1, 8192),
                    "metrics_series_capacity": (1, 4096), "executor_workers": (1, 4), "executor_queue_capacity": (0, 64)}
        for key, number in value["limits"].items():
            if type(number) is not int or not ceilings[key][0] <= number <= ceilings[key][1]:
                raise ValueError
        from discordbot.operations.adapters.filesystem import identifier
        identifier(value["key_id"])
        if not isinstance(value["gemini_model"], str) or not value["gemini_model"].strip():
            raise ValueError
        if value["environment"] == "production":
            # The shipped staging example must never become production merely by
            # changing its environment label. Real resource existence remains a live gate.
            ids = (value["master"], value["admin_channel"],
                   *(item for pairs in channels.values() for pair in pairs for item in pair))
            if (any(item in {1, 2, 3, 4, 5} for item in ids)
                    or origin.hostname in {"localhost", "watch.yourdomain.com"}
                    or origin.hostname.endswith((".invalid", ".example", ".localhost"))
                    or any(placeholder(value[key]) for key in ("public_origin", "gemini_model", "key_id"))
                    or value["key_id"].lower().startswith(("staging", "phase9-synthetic"))):
                raise ConfigurationError("production placeholders must be replaced before startup")
        secret_values = {}
        names = {"discord-bot": ("discord_token", "gemini_key", "control_key"),
                 "watch-web": ("capability_key", "control_key"), "operations": ("db_key",)}[service]
        for name in names:
            text = read_secret(credentials, name)
            if value["environment"] == "production" and (placeholder(text) or text.startswith("fake-")):
                raise ConfigurationError("production secret placeholder refused")
            if name in {"control_key", "capability_key"} and len(text) < 32:
                raise ValueError
            if name == "db_key":
                if len(base64.urlsafe_b64decode(text)) != 32:
                    raise ValueError
                secret_values[name] = text.encode()
            else:
                secret_values[name] = text
        return Settings(service, value["environment"], **parsed, master=value["master"], admin_channel=value["admin_channel"],
                        **channels, public_origin=value["public_origin"], public_port=ports["public"], control_port=ports["control"],
                        discord_health_port=ports["discord_health"], watch_health_port=ports["watch_health"],
                        gemini_model=value["gemini_model"], key_id=value["key_id"],
                        limits=tuple(sorted(value["limits"].items())), secrets=Secrets(**secret_values))
    except ConfigurationError:
        raise
    except (KeyError, ValueError, TypeError, OSError):
        raise ConfigurationError("invalid operations configuration") from None
