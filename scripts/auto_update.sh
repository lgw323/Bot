#!/bin/bash

set -u

# ==========================================
# 고정 운영 경로
# ==========================================
BOT_DIR="/home/os/bot"
DATA_DIR="$BOT_DIR/data"
LOG_FILE="$DATA_DIR/logs/update.log"
PENDING_FILE="$DATA_DIR/update_pending"
STARTUP_REASON_FILE="$DATA_DIR/startup_reason.txt"
VENV_PIP="$BOT_DIR/bot_env/bin/pip"

candidate_requirements=""
update_mode="code"


log_message() {
    local timestamp
    timestamp="$(date "+%Y-%m-%d %H:%M:%S")"
    printf "[%s] %s\n" "$timestamp" "$1" >> "$LOG_FILE"
}


trim_update_log() {
    local line_count

    if [ ! -f "$LOG_FILE" ]; then
        return
    fi

    line_count="$(wc -l < "$LOG_FILE")"
    if [ "$line_count" -gt 1000 ]; then
        tail -n 100 "$LOG_FILE" > "$LOG_FILE.tmp" &&
            mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
}


cleanup() {
    if [ -n "$candidate_requirements" ]; then
        rm -f "$candidate_requirements"
    fi
}


mark_failure() {
    printf "%s\n" "$update_mode" > "$PENDING_FILE"
    log_message "❌ $1 다음 cron 실행에서 다시 시도합니다."
    trim_update_log
    return 1
}


ensure_main_branch() {
    local current_branch

    current_branch="$(git rev-parse --abbrev-ref HEAD)" || return 1
    if [ "$current_branch" = "main" ]; then
        return 0
    fi

    git fetch origin main >> "$LOG_FILE" 2>&1 || return 1
    if git show-ref --verify --quiet refs/heads/main; then
        git checkout main >> "$LOG_FILE" 2>&1
    else
        git checkout -b main --track origin/main >> "$LOG_FILE" 2>&1
    fi
}


prepare_runtime_dependencies() {
    candidate_requirements="$(mktemp "$DATA_DIR/.requirements.XXXXXX")" ||
        return 1
    git show origin/main:requirements.txt > "$candidate_requirements" ||
        return 1

    # -U를 사용하지 않아 이미 조건을 만족하는 일반 패키지는 유지합니다.
    "$VENV_PIP" install -r "$candidate_requirements" >> "$LOG_FILE" 2>&1
}


update_ytdlp() {
    # YouTube 변경 대응이 잦은 yt-dlp만 일일 최신화 대상으로 둡니다.
    "$VENV_PIP" install --upgrade yt-dlp >> "$LOG_FILE" 2>&1
}


cleanup_retired_dependencies() {
    # 새 코드가 정상 기동한 뒤에만 더 이상 사용하지 않는 직접 의존성을 제거합니다.
    if ! "$VENV_PIP" uninstall -y \
        discord-ext-voice-recv \
        SpeechRecognition \
        youtube-search-python \
        pytz \
        google-generativeai >> "$LOG_FILE" 2>&1; then
        log_message "⚠️ 사용 종료 패키지 일부를 정리하지 못했습니다. 봇 실행은 유지합니다."
    fi
}


deploy_code() {
    git reset --hard origin/main >> "$LOG_FILE" 2>&1
}


restart_service() {
    local reason="$1"

    printf "%s\n" "$reason" > "$STARTUP_REASON_FILE"
    if ! sudo systemctl restart discordbot >> "$LOG_FILE" 2>&1; then
        rm -f "$STARTUP_REASON_FILE"
        return 1
    fi

    sleep 3
    if ! sudo systemctl is-active --quiet discordbot; then
        rm -f "$STARTUP_REASON_FILE"
        return 1
    fi
}


rollback_code() {
    local previous_commit="$1"

    if ! git reset --hard "$previous_commit" >> "$LOG_FILE" 2>&1; then
        return 1
    fi

    printf "%s\n" "자동 업데이트 실패 후 이전 코드 복구" \
        > "$STARTUP_REASON_FILE"
    if ! sudo systemctl restart discordbot >> "$LOG_FILE" 2>&1; then
        rm -f "$STARTUP_REASON_FILE"
        return 1
    fi

    sleep 3
    sudo systemctl is-active --quiet discordbot
}


main() {
    local requested_mode="${1:-}"
    local pending_mode=""
    local daily_requested="false"
    local retry_requested="false"
    local local_commit
    local remote_commit
    local previous_commit
    local code_update_needed="false"
    local code_deployed="false"
    local reason

    mkdir -p "$(dirname "$LOG_FILE")"
    cd "$BOT_DIR" || return 1

    if [ -f "$PENDING_FILE" ]; then
        pending_mode="$(head -n 1 "$PENDING_FILE")"
        retry_requested="true"
    fi

    if [ "$requested_mode" = "--daily" ] || [ "$pending_mode" = "daily" ]; then
        daily_requested="true"
        update_mode="daily"
    fi

    if ! ensure_main_branch; then
        mark_failure "main 브랜치 준비에 실패했습니다."
        return 1
    fi

    if ! git fetch origin main >> "$LOG_FILE" 2>&1; then
        mark_failure "원격 main 브랜치 조회에 실패했습니다."
        return 1
    fi

    local_commit="$(git rev-parse HEAD)" || {
        mark_failure "현재 커밋 확인에 실패했습니다."
        return 1
    }
    remote_commit="$(git rev-parse origin/main)" || {
        mark_failure "원격 커밋 확인에 실패했습니다."
        return 1
    }
    previous_commit="$(git rev-parse HEAD)"

    if [ "$local_commit" != "$remote_commit" ]; then
        code_update_needed="true"
        if [ "$daily_requested" != "true" ]; then
            update_mode="code"
        fi
    fi

    if [ "$code_update_needed" != "true" ] &&
       [ "$daily_requested" != "true" ] &&
       [ "$retry_requested" != "true" ]; then
        return 0
    fi

    if [ "$daily_requested" = "true" ]; then
        reason="일일 yt-dlp 점검"
    elif [ "$code_update_needed" = "true" ]; then
        reason="GitHub 코드 변경 감지"
    else
        reason="이전 자동 업데이트 실패 재시도"
    fi
    log_message "🔄 $reason. 업데이트 프로세스를 시작합니다."

    if [ "$code_update_needed" = "true" ]; then
        if ! prepare_runtime_dependencies; then
            mark_failure "새 코드의 일반 의존성 준비에 실패했습니다."
            return 1
        fi
    fi

    if [ "$daily_requested" = "true" ]; then
        if ! update_ytdlp; then
            mark_failure "yt-dlp 최신화에 실패했습니다."
            return 1
        fi
    fi

    if [ "$code_update_needed" = "true" ]; then
        if ! deploy_code; then
            mark_failure "새 코드 배치에 실패했습니다."
            return 1
        fi
        code_deployed="true"
    fi

    if ! restart_service "$reason"; then
        if [ "$code_deployed" = "true" ]; then
            if rollback_code "$previous_commit"; then
                mark_failure "새 코드 재시작 실패로 이전 코드 복구를 완료했습니다."
            else
                mark_failure "새 코드 재시작과 이전 코드 복구가 모두 실패했습니다. 수동 확인이 필요합니다."
            fi
        else
            mark_failure "서비스 재시작에 실패했습니다."
        fi
        return 1
    fi

    cleanup_retired_dependencies
    rm -f "$PENDING_FILE"
    log_message "✅ $reason 완료."
    trim_update_log
    return 0
}


trap cleanup EXIT
main "$@"
