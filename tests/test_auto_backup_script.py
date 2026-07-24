from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "auto_backup.sh"


def read_backup_script() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_backup_generation_failure_stops_before_archiving() -> None:
    """새 덤프 생성 실패 시 이전 파일을 새 백업처럼 업로드하면 안 됩니다."""
    script = read_backup_script()

    assert 'if ! "$BOT_DIR/bot_env/bin/python" -c "' in script
    assert "새 SQL 백업 생성에 실패했습니다" in script
    assert script.index("새 SQL 백업 생성에 실패했습니다") < script.index(
        "ARCHIVE_DIR="
    )


def test_remote_push_failure_returns_an_error() -> None:
    """원격 업로드 실패를 성공으로 보고하면 운영자가 장애를 알 수 없습니다."""
    script = read_backup_script()
    push_section = script.split(
        "# 원격의 db-backup 브랜치로 강제 밀어넣기",
        1,
    )[1]

    assert "if git push --force" in push_section
    assert "업로드 실패" in push_section
    assert "exit 1" in push_section


def test_backup_uses_required_private_remote_instead_of_code_origin() -> None:
    """DB는 공개 코드 origin으로 우회하지 않고 지정된 저장소만 사용해야 합니다."""
    script = read_backup_script()

    assert "DB_BACKUP_REMOTE_URL" in script
    assert "dotenv_values" in script
    assert "git config --get remote.origin.url" not in script
    assert 'REMOTE_URL="https://github.com/lgw323/Bot.git"' not in script
    assert "백업 원격 저장소 주소가 없습니다" in script
