#!/bin/bash

# ==========================================
# 설정 영역
# ==========================================
BOT_DIR="/home/os/bot"
DATA_DIR="$BOT_DIR/data"
LOG_FILE="$BOT_DIR/data/logs/backup.log"

# ==========================================
# 1. 환경 설정 및 이동
# ==========================================
mkdir -p "$(dirname "$LOG_FILE")"
cd "$BOT_DIR" || exit

# ==========================================
# 2. 변경 사항 감지 및 분류
# ==========================================
# 모든 대상 파일을 스테이징 (JSON 데이터 + 로그 파일)
git add "$DATA_DIR"/*.json "$DATA_DIR"/logs/*

# 스테이징된 변경사항이 있는지 확인
if ! git diff --staged --quiet; then
    
    # 어떤 파일이 변경되었는지 목록 추출
    STAGED_FILES=$(git diff --name-only --cached)
    
    # 플래그 설정
    HAS_JSON=$(echo "$STAGED_FILES" | grep ".json")
    HAS_LOGS=$(echo "$STAGED_FILES" | grep "logs/")
    
    # 상황별 커밋 메시지 생성
    if [ -n "$HAS_JSON" ] && [ -n "$HAS_LOGS" ]; then
        MSG_TYPE="User Data & System Logs"
    elif [ -n "$HAS_JSON" ]; then
        MSG_TYPE="User Data Update"
    elif [ -n "$HAS_LOGS" ]; then
        MSG_TYPE="System Logs Archived"
    else
        MSG_TYPE="Routine Backup"
    fi

    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    COMMIT_MSG="Auto-backup: $MSG_TYPE [$TIMESTAMP]"
    
    # 커밋 수행
    git commit -m "$COMMIT_MSG"
    echo "[$TIMESTAMP] 💾 커밋 완료: $MSG_TYPE" >> "$LOG_FILE"
fi

# ==========================================
# 3. GitHub 동기화 (Push Check)
# ==========================================
git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    
    # 충돌 방지 및 업로드
    git pull --rebase origin main
    git push origin main
    
    if [ $? -eq 0 ]; then
        echo "[$TIMESTAMP] ☁️ 업로드 완료." >> "$LOG_FILE"
    else
        echo "[$TIMESTAMP] ❌ 업로드 실패." >> "$LOG_FILE"
    fi
fi
