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
    sqlite3 "$DATA_DIR/bot_database.db" ".backup '$DATA_DIR/temp_backup.db'"
    sqlite3 "$DATA_DIR/temp_backup.db" .dump > "$DATA_DIR/database_backup.sql"
    rm -f "$DATA_DIR/temp_backup.db"
fi

# 모든 대상 파일을 스테이징 (순수 텍스트 백업본)
git add "$DATA_DIR"/*.sql

# 스테이징된 변경사항이 있는지 확인
if ! git diff --staged --quiet; then
    
    # 어떤 파일이 변경되었는지 목록 추출
    STAGED_FILES=$(git diff --name-only --cached)
    
    # 플래그 설정 (.sql 덤프가 포함되었는지 확인)
    HAS_DB=$(echo "$STAGED_FILES" | grep ".sql")
    
    # 상황별 커밋 메시지 생성
    if [ -n "$HAS_DB" ]; then
        MSG_TYPE="User Data Update"
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
