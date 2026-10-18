"""한국어 한 번 입력으로 production 후보만 준비한다. 로그인/배포/dotenv 접근은 하지 않는다."""

from __future__ import annotations

import base64
import getpass
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import warnings
from urllib.parse import urlsplit


TARGET = Path("/etc/discordbot/production-candidate")
DEFAULT_ORIGIN = "https://watch.lgw323.com"
SECRET_NAMES = {"discord_token", "gemini_key", "db_key", "control_key", "capability_key"}


def secret_valid(name: str, value: str) -> bool:
    if (not value or not value.isascii() or len(value) > 4096 or any(c.isspace() for c in value)
            or any(marker in value.lower() for marker in
                   ("censored", "replace_", "your_", "changeme", "placeholder", "fake-"))):
        return False
    if name == "db_key":
        try:
            return len(value) == 44 and len(base64.b64decode(value, altchars=b"-_", validate=True)) == 32
        except ValueError:
            return False
    return name not in {"control_key", "capability_key"} or len(value) >= 32


def ask_secret(name: str, explanation: str) -> str:
    while True:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass(explanation + " (숨김 입력): ").strip()
        if not secret_valid(name, value):
            print("빈 값·템플릿 값 또는 잘못된 형식입니다. 실제 값을 다시 입력해 주세요.")
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            confirmation = getpass.getpass("확인을 위해 같은 값을 한 번 더 입력해 주세요 (숨김 입력): ").strip()
        if value == confirmation:
            return value
        print("두 입력이 다릅니다. 다시 입력해 주세요.")


def ask_id(explanation: str) -> int:
    while True:
        raw = input(explanation + ": ").strip()
        if raw.isascii() and raw.isdecimal() and 5 < int(raw) < 2**63:
            return int(raw)
        print("Discord 개발자 모드의 'ID 복사'로 얻은 정수를 입력해 주세요. 예시 숫자는 사용할 수 없습니다.")


def origin_valid(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                    and not parsed.path and not parsed.query and not parsed.fragment
                    and parsed.hostname not in {"localhost", "127.0.0.1", "::1", "watch.yourdomain.com"}
                    and not parsed.hostname.endswith((".invalid", ".example", ".localhost"))
                    and (parsed.port is None or 1 <= parsed.port <= 65535)
                    and not any(marker in value.lower() for marker in ("replace_", "placeholder")))
    except ValueError:
        return False


def collect(template: dict) -> tuple[dict, dict[str, str]]:
    values = {}
    values["discord_token"] = ask_secret("discord_token", "1. 기존 V1 봇의 Discord 봇 토큰을 입력해 주세요")
    values["gemini_key"] = ask_secret("gemini_key", "2. 기존 V1에서 사용한 Gemini API 키를 입력해 주세요")
    values["db_key"] = ask_secret("db_key", "3. 기존 DB_ENCRYPTION_KEY를 입력해 주세요. 새 키를 만들지 마세요")
    config = json.loads(json.dumps(template))
    config["master"] = ask_id("4. 봇 최고관리자인 본인의 Discord 사용자 ID")
    guild = ask_id("5. 친구들이 봇을 사용하는 Discord 서버(guild) ID")
    main = ask_id("6. 대화 요약과 생일 알림에 함께 사용할 메인 텍스트 채널 ID")
    music = ask_id("7. 기존 음악 전용 jukebox 텍스트 채널 ID")
    config["admin_channel"] = ask_id("8. 개인 관리 서버에서 Watch 알림·강제 종료를 받을 비공개 텍스트 채널 ID")
    config["main_channels"] = [[guild, main]]
    config["music_channels"] = [[guild, music]]
    while True:
        origin = input(f"9. Watch 공개 주소 [Enter 기본값: {DEFAULT_ORIGIN}]: ").strip() or DEFAULT_ORIGIN
        if origin_valid(origin):
            config["public_origin"] = origin
            break
        print("https://도메인 형식으로 입력해 주세요. 끝의 /, 경로, query, 예시 도메인은 제외합니다.")
    values["control_key"] = secrets.token_urlsafe(48)
    values["capability_key"] = secrets.token_urlsafe(48)
    config["key_id"] = "production-key-1"
    config["environment"] = "production"
    print("10. Watch control key: 안전한 새 무작위 키를 자동 생성했습니다. 값은 표시하지 않습니다.")
    print("11. Watch capability key: 별도의 새 무작위 키를 자동 생성했습니다. 값은 표시하지 않습니다.")
    return config, values


def private_file(path: Path, payload: bytes, mode: int, uid: int, gid: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode)
    with os.fdopen(fd, "wb") as stream:
        os.fchown(stream.fileno(), uid, gid)
        os.fchmod(stream.fileno(), mode)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def validate_config(config: dict) -> None:
    expected = {"version", "environment", "paths", "master", "admin_channel", "main_channels", "music_channels",
                "public_origin", "ports", "gemini_model", "key_id", "limits", "backup_remote"}
    paths = {"database": "/var/lib/discordbot/data/bot_database.db", "state": "/var/lib/discordbot/state",
             "cache": "/var/lib/discordbot/cache", "backups": "/var/lib/discordbot/backups",
             "audit": "/var/lib/discordbot/audit", "release_root": "/opt/discordbot",
             "operation_lock": "/var/lib/discordbot/operations.lock"}
    if (set(config) != expected or config["version"] != 1 or config["environment"] != "production"
            or config["paths"] != paths or config["limits"] != {} or config["backup_remote"] is not None
            or config["ports"] != {"public": 9000, "control": 9001, "discord_health": 9010, "watch_health": 9011}
            or config["key_id"] != "production-key-1" or config["gemini_model"] != "gemini-flash-latest"
            or not origin_valid(config["public_origin"])):
        raise ValueError("Unexpected production template")
    ids = [config["master"], config["admin_channel"]]
    for name in ("main_channels", "music_channels"):
        pairs = config[name]
        if not isinstance(pairs, list) or len(pairs) != 1 or not isinstance(pairs[0], list) or len(pairs[0]) != 2:
            raise ValueError("Invalid channel mapping")
        ids.extend(pairs[0])
    if (any(type(value) is not int or not 5 < value < 2**63 for value in ids)
            or config["main_channels"][0][0] != config["music_channels"][0][0]):
        raise ValueError("Invalid resource identity")


def persist(target: Path, config: dict, values: dict[str, str], *, owner: int, group: int) -> None:
    validate_config(config)
    if (set(values) != SECRET_NAMES or not all(secret_valid(name, value) for name, value in values.items())
            or not origin_valid(config["public_origin"]) or config["environment"] != "production"):
        raise ValueError("Incomplete candidate")
    if any(path.is_symlink() for path in (target, *target.parents)):
        raise ValueError("Linked candidate path")
    # Exclusive mkdir is the publication admission gate: never replaces an existing candidate.
    target.mkdir(mode=0o700)
    os.chown(target, owner, group)
    marker = target / ".setup-incomplete"
    private_file(marker, b"Incomplete; do not install or start services.\n", 0o600, owner, owner)
    secret_root = target / "secrets"
    secret_root.mkdir(mode=0o700)
    os.chown(secret_root, owner, owner)
    secret_root.chmod(0o700)
    for name, value in values.items():
        private_file(secret_root / name, (value + "\n").encode("ascii"), 0o600, owner, owner)
    config_path = target / "config.json"
    private_file(config_path, (json.dumps(config, indent=2) + "\n").encode(), 0o640, owner, group)
    if set(path.name for path in secret_root.iterdir()) != SECRET_NAMES:
        raise ValueError("Missing credential")
    for name in SECRET_NAMES:
        path = secret_root / name
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != owner or info.st_gid != owner
                or path.read_text().strip() != values[name]):
            raise ValueError("Credential validation failed")
    info = config_path.stat()
    if (stat.S_IMODE(info.st_mode) != 0o640 or info.st_uid != owner or info.st_gid != group
            or json.loads(config_path.read_text()) != config):
        raise ValueError("Config validation failed")
    target.chmod(0o750)
    for directory, mode, gid in ((target, 0o750, group), (secret_root, 0o700, owner)):
        info = directory.stat()
        if stat.S_IMODE(info.st_mode) != mode or info.st_uid != owner or info.st_gid != gid:
            raise ValueError("Directory validation failed")
    marker.unlink()
    for directory in (secret_root, target, target.parent):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def main() -> int:
    if os.name != "posix" or not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Pi의 직접 SSH 터미널에서 실행해 주세요. 입력 리다이렉션·자동 로그 수집은 사용하지 마세요.")
        return 1
    if os.geteuid() != 0:
        print("후보 파일 권한 설정을 위해 sudo 관리자 인증을 요청합니다. 기존 os 비밀번호를 직접 입력해 주세요.", flush=True)
        os.execvp("sudo", ["sudo", "--", sys.executable, "-I", str(Path(__file__).resolve())])
    import grp
    try:
        group = grp.getgrnam("discordbot").gr_gid
        if TARGET.exists() or TARGET.is_symlink():
            print("기존 production 후보가 있어 보존했습니다. 덮어쓰지 않습니다. 입력 전에 후보 상태를 확인해 주세요.")
            return 1
        if not TARGET.parent.is_dir() or TARGET.parent.is_symlink():
            raise ValueError("Host preparation missing")
        template = json.loads(Path(__file__).with_name("config.template.json").read_text())
        print("Production 후보 설정을 준비합니다. 기존 staging은 유지하며 서비스 로그인·DNS 변경은 하지 않습니다.")
        print("토큰·키는 화면에 표시되지 않습니다. 입력 중 취소하려면 Ctrl+C를 누르세요.")
        config, values = collect(template)
        persist(TARGET, config, values, owner=0, group=group)
    except (Exception, KeyboardInterrupt) as error:
        print(f"준비를 완료하지 못했습니다 ({type(error).__name__}). staging은 변경하지 않았습니다.")
        print("이미 후보 폴더가 생겼다면 .setup-incomplete 상태를 확인해야 합니다. 값은 채팅에 보내지 마세요.")
        return 1
    print("production candidate config: 준비 완료")
    print("Discord secret: 준비 완료")
    print("Gemini secret: 준비 완료")
    print("DB encryption key: 준비 완료")
    print("Watch secrets: 준비 완료")
    print("validation: PASS (기본 형식·누락·파일 권한 검사, 실제 로그인·systemd mount 검증은 별도)")
    print("보관 위치: /etc/discordbot/production-candidate/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
