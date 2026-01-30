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

# [수정된 부분] 깃허브가 다르거나($LOCAL != $REMOTE) 또는(--daily) 옵션이 있을 때 실행
if [ "$LOCAL" != "$REMOTE" ] || [ "$1" == "--daily" ]; then
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    
    # 로그 메시지 구분 (업데이트 vs 정기점검)
    if [ "$1" == "--daily" ]; then
        REASON="일일 정기 점검 (강제 실행)"
    else
        REASON="깃허브 변경 사항 감지"
    fi
    
    echo "[$TIMESTAMP] 🔄 $REASON. 업데이트 프로세스 시작." >> "$LOG_FILE"

    # [데이터 백업] favorites.json이 존재하면 backups 폴더로 복사
    if [ -f "$DATA_DIR/favorites.json" ]; then
        cp "$DATA_DIR/favorites.json" "$BACKUP_DIR/favorites.json.bak"
        echo "[$TIMESTAMP] 💾 로컬 데이터 백업 완료." >> "$LOG_FILE"
    fi

    # 코드 동기화 (이미 최신이면 메세지만 뜨고 넘어감)
    git pull origin main

    # 의존성 패키지 강제 최신화 (-U 옵션 추가됨)
    "$VENV_PIP" install -U -r requirements.txt
    "$VENV_PIP" install -U yt-dlp discord.py

    # 봇 서비스 재시작
    sudo systemctl restart discordbot

    echo "[$TIMESTAMP] ✅ $REASON 완료." >> "$LOG_FILE"
    
    # [로그 관리] 로그가 너무 길어지면(1000줄) 정리
    if [ -f "$LOG_FILE" ] && [ $(wc -l < "$LOG_FILE") -gt 1000 ]; then
        tail -n 100 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
fi