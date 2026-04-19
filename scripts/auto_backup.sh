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
# 2. 데이터베이스 덤프 및 변경 사항 감지
# ==========================================
# SQLite 이진파일(.db)을 봇이 실행중인 상태에서 덤프할 경우 DB is locked 에러 방지를 위해
# 안전한 스냅샷(temp)을 하나 복사한 후, 그 temp에서 텍스트(.sql)를 추출합니다.
if [ -f "$DATA_DIR/bot_database.db" ]; then
    # sqlite3 패키지가 라즈베리파이에 설치되어 있지 않을 경우를 대비하여
    # 파이썬 내장 모듈을 통해 메모리에 스냅샷을 찍고 sql 텍스트로 덤프합니다. (Lock 방지 안전 백업)
    "$BOT_DIR/bot_env/bin/python" -c "
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
"
fi

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

# ==========================================
# 3. 임시 로컬 보관소 롤백용 아카이브 구축 및 빈 깡통 검증
# ==========================================
ARCHIVE_DIR="$DATA_DIR/archives"
mkdir -p "$ARCHIVE_DIR"

if ls "$DATA_DIR"/*.sql 1> /dev/null 2>&1; then
    # 빈 깡통 DB 강제푸시 방지 (용량이 너무 작으면 푸시 차단)
    FILE_SIZE=$(wc -c < "$DATA_DIR/database_backup.sql")
    if [ "$FILE_SIZE" -lt 1024 ]; then
        echo "[$TIMESTAMP] 🔴 치명적 에러: 백업 파일 용량이 비정상적으로 작습니다 ($FILE_SIZE bytes). 빈 깡통 덮어쓰기를 막기 위해 작업을 중단합니다." >> "$LOG_FILE"
        exit 1
    fi
    # 7일 롤백 유지용 로컬 아카이브에 백업
    cp "$DATA_DIR/database_backup.sql" "$ARCHIVE_DIR/database_backup_$(date "+%Y%m%d_%H%M").sql"
    find "$ARCHIVE_DIR" -type f -name "*.sql" -mtime +7 -exec rm {} \;
else
    echo "[$TIMESTAMP] ❌ 백업 파일(.sql)이 존재하지 않아 푸시를 취소합니다." >> "$LOG_FILE"
    exit 1
fi

# ==========================================
# 4. 안전한 임시 상자(mktemp) 생성 및 독립 브랜치(db-backup) Push
# ==========================================
# mktemp를 사용해 충돌 없는 고유 임시 디렉토리 생성
BACKUP_REPO_DIR=$(mktemp -d)
mkdir -p "$BACKUP_REPO_DIR/data"
cp "$DATA_DIR"/database_backup.sql "$BACKUP_REPO_DIR/data/"

cd "$BACKUP_REPO_DIR" || exit

# 일회용 git 초기화
git init --initial-branch=backup 1> /dev/null 2>&1

# 메인 저장소의 리모트 URL 가져오기
REMOTE_URL=$(cd "$BOT_DIR" && git config --get remote.origin.url)
if [ -z "$REMOTE_URL" ]; then
    REMOTE_URL="https://github.com/lgw323/Bot.git"
fi

# 커밋 및 강제 푸시 (과거 기록 덮어쓰기)
git add .
git commit -m "Auto-backup: User Data Update [$TIMESTAMP]" 1> /dev/null 2>&1

# 원격의 db-backup 브랜치로 강제 밀어넣기 (--force)
git push --force "$REMOTE_URL" backup:db-backup

if [ $? -eq 0 ]; then
    echo "[$TIMESTAMP] ☁️ 업로드 완료 (db-backup 브랜치 강제 푸시)." >> "$LOG_FILE"
else
    echo "[$TIMESTAMP] ❌ 업로드 실패 (db-backup 브랜치)." >> "$LOG_FILE"
fi

# 로봇 퇴근 전 빈 상자 파기
rm -rf "$BACKUP_REPO_DIR"
