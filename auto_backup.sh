#!/bin/bash

# 설정
BOT_DIR="/home/os/bot"
DATA_DIR="$BOT_DIR/data"
LOG_FILE="$BOT_DIR/data/logs/backup.log"

cd "$BOT_DIR" || exit

# 1. data 폴더 내의 json 파일만 스테이징
git add "$DATA_DIR"/*.json

# 2. 변경사항이 있는지 확인
if ! git diff --staged --quiet; then
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    
    # 3. 커밋
    git commit -m "Auto-backup: User data update [$TIMESTAMP]"
    
    # 4. 푸시 (충돌 방지 위해 pull --rebase 후 push)
    git pull --rebase origin main
    git push origin main
    
    echo "[$TIMESTAMP] ☁️ 사용자 데이터 GitHub 백업 완료." >> "$LOG_FILE"
fi
