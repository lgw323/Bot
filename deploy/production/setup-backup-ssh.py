"""Operator-only setup for the approved backup repository; never logs private keys."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path("/etc/discordbot/backup-ssh-candidate")
# Public host key from GitHub's official SSH fingerprints page, checked 2026-09-17.
HOST_KEY = "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n"


def main() -> None:
    if os.name != "posix" or not sys.stdin.isatty():
        raise SystemExit("Pi SSH 터미널에서 직접 실행해 주세요.")
    if os.geteuid() != 0:
        os.execvp("sudo", ["sudo", "--", sys.executable, "-I", str(Path(__file__).resolve())])
    # A fresh directory prevents overwriting a previous key or the active config.
    ROOT.mkdir(mode=0o700)
    os.umask(0o077)
    key = ROOT / "id_ed25519"
    result = subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C",
                             "discordbot-v2-backup-only", "-f", str(key)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    if result.returncode:
        raise SystemExit("키 생성 실패. 기존 디렉터리를 자동 삭제하지 않습니다.")
    key.chmod(0o600)
    (ROOT / "known_hosts").write_text(HOST_KEY, encoding="ascii")
    (ROOT / "known_hosts").chmod(0o600)
    print("백업 전용 SSH 키: 준비 완료 (private key는 표시하지 않습니다)")
    print("GitHub Bot-Data → Settings → Deploy keys → Add deploy key")
    print("Title: DiscordBot V2 backup (Pi)")
    print("Allow write access를 선택하고 아래 공개키만 Key 칸에 붙여 넣으세요.")
    print(key.with_suffix(".pub").read_text(encoding="ascii").strip())
    print("공개키 끝. 등록 완료 여부만 알려주세요. 자동 백업은 아직 활성화하지 않았습니다.")


if __name__ == "__main__":
    main()
