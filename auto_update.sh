#!/bin/bash

# ==========================================
# 설정 영역
# ==========================================
BOT_DIR="/home/os/bot"
LOG_FILE="$BOT_DIR/data/logs/update.log"
DATA_DIR="$BOT_DIR/data"
BACKUP_DIR="$BOT_DIR/backups"
VENV_PIP="$BOT_DIR/bot_env/bin/pip"

# ==========================================
# 1. 초기화 및 브랜치 확인
# ==========================================
mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"
cd "$BOT_DIR" || exit

# 현재 브랜치가 main인지 확인하고 아니면 전환
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ]; then
    git fetch origin main
    git checkout main 2>/dev/null || git checkout -b main origin/main
fi

# ==========================================
# 2. 업데이트 감지 로직
# ==========================================
git fetch origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    echo "[$TIMESTAMP] 🔄 변경 사항 감지. 업데이트 프로세스 시작." >> "$LOG_FILE"

    # [데이터 백업] favorites.json이 존재하면 backups 폴더로 복사
    if [ -f "$DATA_DIR/favorites.json" ]; then
        cp "$DATA_DIR/favorites.json" "$BACKUP_DIR/favorites.json.bak"
        echo "[$TIMESTAMP] 💾 로컬 데이터 백업 완료." >> "$LOG_FILE"
    fi

    # 코드 동기화
    git pull origin main

    # 의존성 패키지 최신화
    "$VENV_PIP" install -r requirements.txt

    # 봇 서비스 재시작
    sudo systemctl restart discordbot

    echo "[$TIMESTAMP] ✅ 업데이트 및 재시작 완료." >> "$LOG_FILE"
    
    # [로그 관리] 로그가 너무 길어지면(1000줄) 정리
    if [ -f "$LOG_FILE" ] && [ $(wc -l < "$LOG_FILE") -gt 1000 ]; then
        tail -n 100 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
fi
