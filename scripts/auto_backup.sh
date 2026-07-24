#!/bin/bash

set -u

# ==========================================
# 고정 운영 경로
# ==========================================
BOT_DIR="/home/os/bot"
DATA_DIR="$BOT_DIR/data"
LOG_FILE="$DATA_DIR/logs/backup.log"
BACKUP_REPO_DIR=""
TIMESTAMP=""


cleanup() {
    if [ -n "$BACKUP_REPO_DIR" ] &&
       [ -d "$BACKUP_REPO_DIR" ]; then
        rm -rf -- "$BACKUP_REPO_DIR"
    fi
}


log_failure() {
    echo "[$TIMESTAMP] ❌ $1" >> "$LOG_FILE"
    exit 1
}


trap cleanup EXIT

# ==========================================
# 1. 환경 설정 및 이동
# ==========================================
mkdir -p "$(dirname "$LOG_FILE")" || exit 1
cd "$BOT_DIR" || exit 1
TIMESTAMP="$(date "+%Y-%m-%d %H:%M:%S")"

# ==========================================
# 2. 암호화 SQL 덤프 생성
# ==========================================
if [ -f "$DATA_DIR/bot_database.db" ]; then
    if ! "$BOT_DIR/bot_env/bin/python" -c "
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

bot_dir = Path('$BOT_DIR')
load_dotenv(dotenv_path=bot_dir / '.env')

import database_manager

try:
    success = asyncio.run(database_manager.backup_database_to_sql())
    if not success:
        sys.exit('Backup Error: backup_database_to_sql returned False')
except Exception as e:
    sys.exit(f'Backup Error: {e}')
"; then
        log_failure "새 SQL 백업 생성에 실패했습니다. 기존 백업 업로드를 중단합니다."
    fi
fi

# ==========================================
# 3. 로컬 7일 보관 및 크기 검증
# ==========================================
ARCHIVE_DIR="$DATA_DIR/archives"
mkdir -p "$ARCHIVE_DIR" ||
    log_failure "로컬 백업 보관 폴더를 만들 수 없습니다."

if [ ! -f "$DATA_DIR/database_backup.sql" ]; then
    log_failure "백업 파일이 없어 원격 업로드를 취소합니다."
fi

FILE_SIZE="$(wc -c < "$DATA_DIR/database_backup.sql")" ||
    log_failure "백업 파일 크기를 확인할 수 없습니다."
if [ "$FILE_SIZE" -lt 1024 ]; then
    log_failure "백업 파일 크기가 비정상적입니다 (${FILE_SIZE} bytes)."
fi

cp "$DATA_DIR/database_backup.sql" \
    "$ARCHIVE_DIR/database_backup_$(date "+%Y%m%d_%H%M").sql" ||
    log_failure "로컬 7일 보관용 백업을 만들 수 없습니다."

if ! find "$ARCHIVE_DIR" -type f -name "*.sql" -mtime +7 -exec rm {} \;; then
    echo "[$TIMESTAMP] ⚠️ 7일이 지난 로컬 백업 정리에 실패했습니다." \
        >> "$LOG_FILE"
fi

# ==========================================
# 4. 독립 임시 저장소에서 db-backup 브랜치 갱신
# ==========================================
BACKUP_REPO_DIR="$(mktemp -d)" ||
    log_failure "임시 백업 저장소를 만들 수 없습니다."
mkdir -p "$BACKUP_REPO_DIR/data" ||
    log_failure "임시 백업 데이터 폴더를 만들 수 없습니다."
cp "$DATA_DIR/database_backup.sql" "$BACKUP_REPO_DIR/data/" ||
    log_failure "임시 백업 저장소로 SQL 파일을 복사할 수 없습니다."
cd "$BACKUP_REPO_DIR" ||
    log_failure "임시 백업 저장소에 접근할 수 없습니다."

git init --initial-branch=backup > /dev/null 2>&1 ||
    log_failure "임시 Git 저장소 초기화에 실패했습니다."

REMOTE_URL="$(cd "$BOT_DIR" && git config --get remote.origin.url)"
if [ -z "$REMOTE_URL" ]; then
    REMOTE_URL="https://github.com/lgw323/Bot.git"
fi

git add . ||
    log_failure "원격 백업 커밋 준비에 실패했습니다."
git commit -m "Auto-backup: User Data Update [$TIMESTAMP]" \
    > /dev/null 2>&1 ||
    log_failure "원격 백업 커밋 생성에 실패했습니다."

# 원격의 db-backup 브랜치로 강제 밀어넣기 (--force)
if git push --force "$REMOTE_URL" backup:db-backup; then
    echo "[$TIMESTAMP] ☁️ 업로드 완료 (db-backup 브랜치 강제 푸시)." \
        >> "$LOG_FILE"
else
    echo "[$TIMESTAMP] ❌ 업로드 실패 (db-backup 브랜치)." \
        >> "$LOG_FILE"
    exit 1
fi
