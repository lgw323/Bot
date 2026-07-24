from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "auto_update.sh"


def read_update_script() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_only_ytdlp_is_force_upgraded() -> None:
    """일일 점검이 일반 라이브러리나 discord.py를 무조건 갱신하면 안 됩니다."""
    script = read_update_script()

    assert 'install -r "$candidate_requirements"' in script
    assert "install -U -r" not in script
    assert "install -U yt-dlp discord.py" not in script
    assert 'install --upgrade yt-dlp' in script


def test_dependencies_are_prepared_before_code_is_deployed() -> None:
    """패키지 준비 실패 전에는 현재 실행 코드를 바꾸지 않아야 합니다."""
    script = read_update_script()
    update_flow = script.split("main() {", 1)[1]

    prepare_index = update_flow.index("prepare_runtime_dependencies")
    ytdlp_index = update_flow.index("update_ytdlp")
    deploy_index = update_flow.index("deploy_code")

    assert prepare_index < deploy_index
    assert ytdlp_index < deploy_index


def test_failed_update_is_logged_and_marked_for_retry() -> None:
    """실패는 종료 코드와 재시도 표식으로 남고 재시작까지 진행되면 안 됩니다."""
    script = read_update_script()

    assert 'printf "%s\\n" "$update_mode" > "$PENDING_FILE"' in script
    assert "다음 cron 실행에서 다시 시도합니다" in script
    assert "return 1" in script
    assert 'if ! restart_service "$reason"; then' in script


def test_restart_failure_rolls_back_changed_code() -> None:
    """새 코드 재시작이 실패하면 직전 커밋으로 되돌릴 경로가 있어야 합니다."""
    script = read_update_script()

    assert 'previous_commit="$(git rev-parse HEAD)"' in script
    assert 'rollback_code "$previous_commit"' in script
    assert "이전 코드 복구" in script


def test_retired_packages_are_removed_only_after_successful_restart() -> None:
    """사용하지 않는 패키지는 새 코드가 정상 기동한 뒤에만 정리해야 합니다."""
    script = read_update_script()
    update_flow = script.split("main() {", 1)[1]

    restart_index = update_flow.index('restart_service "$reason"')
    cleanup_index = update_flow.index("cleanup_retired_dependencies")

    assert restart_index < cleanup_index
    for package in (
        "discord-ext-voice-recv",
        "SpeechRecognition",
        "youtube-search-python",
        "pytz",
        "google-generativeai",
    ):
        assert package in script
