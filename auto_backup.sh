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
# 로그 디렉토리가 없으면 생성
mkdir -p "$(dirname "$LOG_FILE")"
cd "$BOT_DIR" || exit

# ==========================================
# 2. 변경 사항 커밋 (Staging & Commit)
# ==========================================
# json 파일과 logs 폴더 전체를 스테이징
git add "$DATA_DIR"/*.json "$DATA_DIR"/logs/*

# 스테이징된 변경사항이 있다면 커밋
if ! git diff --staged --quiet; then
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    git commit -m "Auto-backup: User data update [$TIMESTAMP]"
    echo "[$TIMESTAMP] 💾 로컬 저장소에 새로운 데이터 커밋 완료." >> "$LOG_FILE"
fi

# ==========================================
# 3. GitHub 동기화 (Push Check)
# ==========================================
# 원격 상태 최신화
git fetch origin main

# 로컬과 원격의 해시 비교
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

# 로컬이 원격과 다르다면 (앞서 있다면) 업로드 수행
if [ "$LOCAL" != "$REMOTE" ]; then
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    
    # 충돌 방지 및 업로드
    git pull --rebase origin main
    git push origin main
    
    if [ $? -eq 0 ]; then
        echo "[$TIMESTAMP] ☁️ GitHub로 데이터 업로드(동기화) 완료." >> "$LOG_FILE"
    else
        echo "[$TIMESTAMP] ❌ GitHub 업로드 실패. 네트워크나 인증을 확인하세요." >> "$LOG_FILE"
    fi
fi
