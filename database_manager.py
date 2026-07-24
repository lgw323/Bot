import asyncio
import base64
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

# --- 봇 전용 SQLite 연결 ---
def _configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    """전역 sqlite3 동작을 바꾸지 않고 봇 연결에만 PRAGMA를 적용합니다."""
    try:
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA cache_size=-2000;")
    except Exception as e:
        logging.getLogger("DatabaseManager").warning(f"SQLite PRAGMA optimization failed: {e}")
    return conn

logger: logging.Logger = logging.getLogger("DatabaseManager")

# 현재 스크립트 위치 기준으로 절대 경로 설정
BASE_DIR: Path = Path(__file__).parent
DATA_DIR: Path = BASE_DIR / "data"

DB_PATH: Path = DATA_DIR / "bot_database.db"
SQL_BACKUP_PATH: Path = DATA_DIR / "database_backup.sql"
BACKUP_ENVELOPE_HEADER: bytes = b"DISCORDBOT_BACKUP_V2\n"


def _connect_database(path: Optional[Path] = None) -> sqlite3.Connection:
    """봇 데이터베이스 연결을 열고 공통 세션 설정을 적용합니다."""
    target_path = DB_PATH if path is None else path
    conn = sqlite3.connect(
        target_path,
        timeout=10.0,
        check_same_thread=False,
    )
    return _configure_connection(conn)


# 기존 JSON 경로는 더 이상 사용하지 않아 삭제됨

# SQLite 동시성 이슈(Concurrency)를 방어하기 위해 db_lock을 사용합니다.
# 또한 check_same_thread=False 옵션을 추가하여 asyncio.to_thread에서 발생할 수 있는 스레드 참조 에러를 최적화합니다.
db_lock: asyncio.Lock = asyncio.Lock()

# 암호화 인스턴스 초기화
_cipher_suite: Optional[Fernet] = None
def get_cipher() -> Optional[Fernet]:
    global _cipher_suite
    if _cipher_suite is None:
        key = os.environ.get("DB_ENCRYPTION_KEY")
        if key:
            try:
                _cipher_suite = Fernet(key.encode('utf-8'))
            except Exception as e:
                logger.error(f"Invalid DB_ENCRYPTION_KEY format: {e}")
                return None
        else:
            logger.warning(
                "DB_ENCRYPTION_KEY not found in environment variables. "
                "Protected backup data cannot be encrypted or decrypted."
            )
            return None
    return _cipher_suite

def _parse_dump_values(line: str) -> tuple[Any, ...]:
    """Parse SQLite's own VALUES syntax without treating it as Python code."""
    parts = line.split("VALUES(", 1)
    if len(parts) != 2 or ");" not in parts[1]:
        raise ValueError("Unsupported SQL dump INSERT format.")

    value_part = parts[1].rsplit(");", 1)[0]
    with sqlite3.connect(":memory:") as parser:
        row = parser.execute(f"SELECT {value_part}").fetchone()

    if row is None:
        raise ValueError("SQL dump INSERT has no values.")
    return tuple(row)


def _looks_like_fernet_token(value: Any) -> bool:
    """Recognize encrypted backup values while allowing legacy plain text."""
    if not isinstance(value, str):
        return False

    try:
        raw_token = base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False

    return len(raw_token) >= 73 and raw_token[0] == 0x80


def _decode_backup_value(value: Any) -> str:
    """Decrypt protected dump data or reject an unreadable encrypted value."""
    text = str(value)
    if not _looks_like_fernet_token(text):
        return text

    cipher = get_cipher()
    if cipher is None:
        raise ValueError("DB_ENCRYPTION_KEY is required to restore encrypted data.")

    try:
        return cipher.decrypt(text.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError(
            "DB_ENCRYPTION_KEY cannot decrypt the protected backup data."
        ) from e


def _fetch_remote_backup() -> None:
    """Fetch the current SQL dump from the dedicated private repository."""
    remote_url = os.environ.get("DB_BACKUP_REMOTE_URL", "").strip()
    if not remote_url:
        logger.critical(
            "DB_BACKUP_REMOTE_URL is required for remote database recovery."
        )
        sys.exit(
            "System Halt: DB_BACKUP_REMOTE_URL is required for private "
            "database backup recovery."
        )

    logger.info(
        "Local DB and backup SQL not found. Attempting to fetch the private "
        "'db-backup' branch..."
    )
    try:
        subprocess.run(
            [
                "git",
                "fetch",
                "--no-tags",
                remote_url,
                "db-backup",
            ],
            check=True,
            cwd=BASE_DIR,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "show", "FETCH_HEAD:data/database_backup.sql"],
            check=True,
            cwd=BASE_DIR,
            capture_output=True,
        )
        SQL_BACKUP_PATH.write_bytes(result.stdout)
        logger.info("Successfully fetched database_backup.sql from remote branch without polluting Index!")
    except Exception as e:
        logger.critical(f"FATAL Error fetching backup: {e}")
        sys.exit(
            "System Halt: Empty DB creation blocked due to remote fetch failure. "
            "Check DB_BACKUP_REMOTE_URL, credentials, network, or the "
            "db-backup branch."
        )


def _decode_backup_line(line: str) -> str:
    """Decrypt the protected values in one supported SQLite dump line."""
    if line.startswith("INSERT INTO \"favorites\" VALUES("):
        user_id, enc_url, enc_title = _parse_dump_values(line)
        dec_url = _decode_backup_value(enc_url).replace("'", "''")
        dec_title = _decode_backup_value(enc_title).replace("'", "''")
        return (
            f"INSERT INTO \"favorites\" VALUES("
            f"{user_id},'{dec_url}','{dec_title}');\n"
        )

    elif line.startswith("INSERT INTO \"music_play_counts\" VALUES("):
        guild_id, enc_url, enc_title, play_count = _parse_dump_values(line)
        dec_url = _decode_backup_value(enc_url).replace("'", "''")
        dec_title = _decode_backup_value(enc_title).replace("'", "''")
        return (
            f"INSERT INTO \"music_play_counts\" VALUES("
            f"{guild_id},'{dec_url}','{dec_title}',{play_count});\n"
        )

    return line


def _restore_database_from_sql() -> None:
    """Restore into a temporary DB and publish it only after full success."""
    logger.info(f"Main DB not found. Restoring from {SQL_BACKUP_PATH}...")
    temp_path: Optional[Path] = None

    try:
        backup_bytes = SQL_BACKUP_PATH.read_bytes()
        if backup_bytes.startswith(BACKUP_ENVELOPE_HEADER):
            cipher = get_cipher()
            if cipher is None:
                raise ValueError(
                    "DB_ENCRYPTION_KEY is required to restore this backup."
                )

            encrypted_payload = backup_bytes[len(BACKUP_ENVELOPE_HEADER):]
            try:
                sql_script = cipher.decrypt(encrypted_payload).decode("utf-8")
            except (InvalidToken, UnicodeDecodeError) as e:
                raise ValueError(
                    "DB_ENCRYPTION_KEY cannot decrypt this backup."
                ) from e
        else:
            legacy_script = backup_bytes.decode("utf-8")
            sql_script = "".join(
                _decode_backup_line(line)
                for line in legacy_script.splitlines(keepends=True)
            )

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=DB_PATH.parent,
            prefix=f".{DB_PATH.stem}.restore.",
            suffix=".db",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

        conn = _connect_database(temp_path)
        try:
            conn.executescript(sql_script)
            conn.commit()
        finally:
            conn.close()

        os.replace(temp_path, DB_PATH)
        temp_path = None
        logger.info("Database restored successfully from SQL dump.")
    except Exception as e:
        logger.error(f"Failed to restore DB: {e}", exc_info=True)
        raise RuntimeError(f"Failed to restore DB from {SQL_BACKUP_PATH}") from e
    finally:
        if temp_path is not None:
            for candidate in (
                temp_path,
                Path(f"{temp_path}-journal"),
                Path(f"{temp_path}-wal"),
                Path(f"{temp_path}-shm"),
            ):
                candidate.unlink(missing_ok=True)


def _prepare_database_schema() -> None:
    """Apply persistent DB settings, create tables, and run compatible upgrades."""
    with _connect_database() as conn:
        # journal_mode는 데이터베이스 파일에 영구 기록되므로 초기화 시 한 번만 설정합니다.
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception as e:
            logger.warning(f"Failed to set journal_mode to WAL: {e}")
        c: sqlite3.Cursor = conn.cursor()
        
        # 1. users
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                guild_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                total_vc_seconds INTEGER DEFAULT 0,
                birth_month INTEGER,
                birth_day INTEGER,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')
        
        # 레거시 users 테이블 구조에 생일 컬럼이 없다면 자동 추가
        c.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in c.fetchall()]
        if 'birth_month' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN birth_month INTEGER")
            c.execute("ALTER TABLE users ADD COLUMN birth_day INTEGER")
        
        # 2. music_settings (guild 단위)
        c.execute('''
            CREATE TABLE IF NOT EXISTS music_settings (
                guild_id INTEGER PRIMARY KEY,
                volume REAL DEFAULT 1.0
            )
        ''')
        
        # 3. music_play_counts (guild 단위)
        c.execute('''
            CREATE TABLE IF NOT EXISTS music_play_counts (
                guild_id INTEGER,
                url TEXT,
                title TEXT,
                play_count INTEGER DEFAULT 1,
                PRIMARY KEY(guild_id, url)
            )
        ''')
        
        # 4. favorites (user 단위)
        c.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER,
                url TEXT,
                title TEXT,
                PRIMARY KEY(user_id, url)
            )
        ''')
        
        # 5. watch_sessions (방 정보)
        c.execute('''
            CREATE TABLE IF NOT EXISTS watch_sessions (
                session_id TEXT PRIMARY KEY,
                guild_id INTEGER,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                channel_id INTEGER,
                message_id INTEGER
            )
        ''')
        
        # 기존 테이블에 컬럼이 없을 시 자동 추가
        c.execute("PRAGMA table_info(watch_sessions)")
        watch_columns = [info[1] for info in c.fetchall()]
        if 'channel_id' not in watch_columns:
            c.execute("ALTER TABLE watch_sessions ADD COLUMN channel_id INTEGER")
            c.execute("ALTER TABLE watch_sessions ADD COLUMN message_id INTEGER")
        
        # 6. watch_playlists (세션 공유 대기열)
        c.execute('''
            CREATE TABLE IF NOT EXISTS watch_playlists (
                session_id TEXT,
                video_url TEXT,
                video_title TEXT,
                added_by TEXT,
                order_index INTEGER,
                PRIMARY KEY (session_id, video_url)
            )
        ''')
        
        conn.commit()
    logger.info("Database schemas initialized.")


def init_db() -> None:
    """Prepare local storage, recover data when needed, and ensure the schema."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists() and not SQL_BACKUP_PATH.exists():
        _fetch_remote_backup()

    if not DB_PATH.exists() and SQL_BACKUP_PATH.exists():
        _restore_database_from_sql()

    _prepare_database_schema()


def _write_database_dump(destination: Path) -> None:
    """Write one complete plaintext SQL dump to a protected temporary path."""
    with _connect_database() as conn:
        with destination.open("w", encoding="utf-8", newline="\n") as dump_file:
            for line in conn.iterdump():
                dump_file.write(f"{line}\n")


def _validate_sql_backup(backup_path: Path) -> None:
    """Reject incomplete or syntactically invalid SQL dumps."""
    sql_script = backup_path.read_text(encoding="utf-8")
    if "BEGIN TRANSACTION;" not in sql_script or "COMMIT;" not in sql_script:
        raise ValueError("SQL backup is missing transaction boundaries.")

    with sqlite3.connect(":memory:") as validation_db:
        validation_db.executescript(sql_script)


def _create_atomic_database_backup() -> bool:
    """Validate, encrypt, and publish a complete backup as one atomic file."""
    cipher = get_cipher()
    if cipher is None:
        logger.error(
            "Database backup aborted because DB_ENCRYPTION_KEY is missing "
            "or invalid."
        )
        return False

    SQL_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    plaintext_temp_path: Optional[Path] = None
    encrypted_temp_path: Optional[Path] = None

    try:
        with tempfile.NamedTemporaryFile(
            dir=SQL_BACKUP_PATH.parent,
            prefix=f".{SQL_BACKUP_PATH.stem}.plaintext.",
            suffix=".sql.tmp",
            delete=False,
        ) as temp_file:
            plaintext_temp_path = Path(temp_file.name)

        with tempfile.NamedTemporaryFile(
            dir=SQL_BACKUP_PATH.parent,
            prefix=f".{SQL_BACKUP_PATH.stem}.encrypted.",
            suffix=".enc.tmp",
            delete=False,
        ) as temp_file:
            encrypted_temp_path = Path(temp_file.name)

        _write_database_dump(plaintext_temp_path)
        _validate_sql_backup(plaintext_temp_path)

        plaintext_bytes = plaintext_temp_path.read_bytes()
        encrypted_payload = cipher.encrypt(plaintext_bytes)
        if cipher.decrypt(encrypted_payload) != plaintext_bytes:
            raise ValueError("Encrypted backup verification failed.")

        encrypted_temp_path.write_bytes(
            BACKUP_ENVELOPE_HEADER + encrypted_payload
        )
        os.replace(encrypted_temp_path, SQL_BACKUP_PATH)
        encrypted_temp_path = None
        logger.info("Database successfully backed up as an encrypted envelope.")
        return True
    except Exception as e:
        logger.error(f"Failed to backup DB to SQL: {e}", exc_info=True)
        return False
    finally:
        for temp_path in (plaintext_temp_path, encrypted_temp_path):
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


async def backup_database_to_sql() -> bool:
    """Create an encrypted SQL backup without risking the last good dump."""
    async with db_lock:
        return await asyncio.to_thread(_create_atomic_database_backup)


# migrate_json_to_db() 함수는 불필요해져 삭제되었습니다.


# 비동기 DB 조회/조작 유틸 함수
async def get_favorites() -> Dict[str, List[Dict[str, str]]]:
    async with db_lock:
        def _get() -> Dict[str, List[Dict[str, str]]]:
            with _connect_database() as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                c.execute("SELECT user_id, url, title FROM favorites")
                res: Dict[str, List[Dict[str, str]]] = {}
                for row in c.fetchall():
                    uid: str = str(row['user_id'])
                    if uid not in res:
                        res[uid] = []
                    res[uid].append({"url": row['url'], "title": row['title']})
                return res
        return await asyncio.to_thread(_get)


async def add_favorite(user_id: int, url: str, title: str) -> None:
    async with db_lock:
        def _add() -> None:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, 0))
                c.execute("INSERT OR REPLACE INTO favorites (user_id, url, title) VALUES (?, ?, ?)", (user_id, url, title))
                conn.commit()
        await asyncio.to_thread(_add)


async def remove_favorites(user_id: int, urls: List[str]) -> int:
    async with db_lock:
        def _remove() -> int:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                deleted_count: int = 0
                for url in urls:
                    c.execute("DELETE FROM favorites WHERE user_id = ? AND url = ?", (user_id, url))
                    deleted_count += c.rowcount
                conn.commit()
                return deleted_count
        return await asyncio.to_thread(_remove)


async def get_music_settings() -> Dict[str, Any]:
    async with db_lock:
        def _get() -> Dict[str, Any]:
            with _connect_database() as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                res: Dict[str, Any] = {}
                c.execute("SELECT guild_id, volume FROM music_settings")
                for row in c.fetchall():
                    gid: str = str(row['guild_id'])
                    if gid not in res:
                        res[gid] = {"play_counts": {}}
                    res[gid]["volume"] = row['volume']
                
                c.execute("SELECT guild_id, url, title, play_count FROM music_play_counts")
                for row in c.fetchall():
                    gid: str = str(row['guild_id'])
                    if gid not in res:
                        res[gid] = {"volume": 1.0, "play_counts": {}}
                    if "play_counts" not in res[gid]:
                        res[gid]["play_counts"] = {}
                    res[gid]["play_counts"][row['url']] = {"title": row['title'], "count": row['play_count']}
                return res
        return await asyncio.to_thread(_get)


async def update_music_volume(guild_id: int, volume: float) -> None:
    async with db_lock:
        def _update() -> None:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("INSERT OR IGNORE INTO music_settings (guild_id, volume) VALUES (?, ?)", (guild_id, volume))
                c.execute("UPDATE music_settings SET volume = ? WHERE guild_id = ?", (volume, guild_id))
                conn.commit()
        await asyncio.to_thread(_update)


async def increment_play_count_db(guild_id: int, url: str, title: str) -> None:
    async with db_lock:
        def _update() -> None:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("INSERT OR IGNORE INTO music_play_counts (guild_id, url, title, play_count) VALUES (?, ?, ?, 0)", (guild_id, url, title))
                c.execute("UPDATE music_play_counts SET play_count = play_count + 1, title = ? WHERE guild_id = ? AND url = ?", (title, guild_id, url))
                
                c.execute("SELECT url FROM music_play_counts WHERE guild_id = ? ORDER BY play_count DESC LIMIT -1 OFFSET 50", (guild_id,))
                to_delete: List[str] = [r[0] for r in c.fetchall()]
                for del_url in to_delete:
                    c.execute("DELETE FROM music_play_counts WHERE guild_id = ? AND url = ?", (guild_id, del_url))
                conn.commit()
        await asyncio.to_thread(_update)


async def get_top_played_songs_db(guild_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    async with db_lock:
        def _get() -> List[Dict[str, Any]]:
            with _connect_database() as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                c.execute("SELECT url, title, play_count as count FROM music_play_counts WHERE guild_id = ? ORDER BY play_count DESC LIMIT ?", (guild_id, limit))
                return [dict(row) for row in c.fetchall()]
        return await asyncio.to_thread(_get)


# ==========================================
# 레벨링 영역 DB 함수 (Users 테이블)
# ==========================================

async def get_user_data(user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
    async with db_lock:
        def _get() -> Optional[Dict[str, Any]]:
            with _connect_database() as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                c.execute("SELECT user_id, guild_id, xp, level, total_vc_seconds FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
                row = c.fetchone()
                return dict(row) if row else None
        return await asyncio.to_thread(_get)


async def update_user_xp(user_id: int, guild_id: int, xp_added: int, vc_sec_added: int = 0, new_level: Optional[int] = None) -> None:
    async with db_lock:
        def _update() -> None:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                
                # 먼저 데이터가 있는지 검사하고 없으면 기본값으로 생성
                c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))

                if new_level is not None:
                    c.execute("UPDATE users SET xp = xp + ?, total_vc_seconds = total_vc_seconds + ?, level = ? WHERE user_id = ? AND guild_id = ?",
                              (xp_added, vc_sec_added, new_level, user_id, guild_id))
                else:
                    c.execute("UPDATE users SET xp = xp + ?, total_vc_seconds = total_vc_seconds + ? WHERE user_id = ? AND guild_id = ?",
                              (xp_added, vc_sec_added, user_id, guild_id))
                conn.commit()
        await asyncio.to_thread(_update)


async def get_top_users(guild_id: int, limit: int = 10, vc_xp_per_min: int = 5) -> List[Dict[str, Any]]:
    async with db_lock:
        def _get() -> List[Dict[str, Any]]:
            with _connect_database() as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                
                # 순수하게 현재 서버(guild_id)의 데이터만 가져와 랭킹을 산정합니다.
                c.execute('''
                    SELECT user_id, xp, level, total_vc_seconds,
                           (xp + (total_vc_seconds / 60) * ?) as total_xp
                    FROM users 
                    WHERE guild_id = ?
                    ORDER BY total_xp DESC
                    LIMIT ?
                ''', (vc_xp_per_min, guild_id, limit))
                
                rows: List[Dict[str, Any]] = [dict(row) for row in c.fetchall()]
                return rows
        return await asyncio.to_thread(_get)

# ==========================================
# 생일 기능 DB 함수
# ==========================================

async def add_birthday(user_id: int, guild_id: int, month: int, day: int) -> None:
    async with db_lock:
        def _add() -> None:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
                c.execute("UPDATE users SET birth_month = ?, birth_day = ? WHERE user_id = ? AND guild_id = ?", (month, day, user_id, guild_id))
                conn.commit()
        await asyncio.to_thread(_add)

async def remove_birthday(user_id: int, guild_id: int) -> int:
    async with db_lock:
        def _remove() -> int:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("UPDATE users SET birth_month = NULL, birth_day = NULL WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
                updated = c.rowcount
                conn.commit()
                return updated
        return await asyncio.to_thread(_remove)

async def get_birthdays_today(guild_id: int, month: int, day: int) -> List[int]:
    async with db_lock:
        def _get() -> List[int]:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("SELECT user_id FROM users WHERE guild_id = ? AND birth_month = ? AND birth_day = ?", (guild_id, month, day))
                return [row[0] for row in c.fetchall()]
        return await asyncio.to_thread(_get)

async def get_all_birthdays(guild_id: int) -> List[Dict[str, int]]:
    async with db_lock:
        def _get() -> List[Dict[str, int]]:
            with _connect_database() as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                c.execute("SELECT user_id, birth_month as month, birth_day as day FROM users WHERE guild_id = ? AND birth_month IS NOT NULL ORDER BY birth_month, birth_day", (guild_id,))
                return [dict(row) for row in c.fetchall()]
        return await asyncio.to_thread(_get)


# ==========================================
# 동시 시청 (Watch Together) 영역 DB 함수
# ==========================================

async def add_watch_session(session_id: str, guild_id: int, created_by: int, channel_id: Optional[int] = None, message_id: Optional[int] = None) -> None:
    async with db_lock:
        def _add() -> None:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute(
                    "INSERT OR REPLACE INTO watch_sessions (session_id, guild_id, created_by, channel_id, message_id) VALUES (?, ?, ?, ?, ?)",
                    (session_id, guild_id, created_by, channel_id, message_id)
                )
                conn.commit()
        await asyncio.to_thread(_add)


async def get_watch_session(session_id: str) -> Optional[Dict[str, Any]]:
    async with db_lock:
        def _get() -> Optional[Dict[str, Any]]:
            with _connect_database() as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                c.execute("SELECT session_id, guild_id, created_by, created_at, channel_id, message_id FROM watch_sessions WHERE session_id = ?", (session_id,))
                row = c.fetchone()
                return dict(row) if row else None
        return await asyncio.to_thread(_get)


async def get_all_watch_sessions() -> List[Dict[str, Any]]:
    """Return all persisted Watch Together sessions for startup reconciliation."""
    async with db_lock:
        def _get() -> List[Dict[str, Any]]:
            with _connect_database() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT session_id, guild_id, created_by, created_at,
                           channel_id, message_id
                    FROM watch_sessions
                    ORDER BY created_at ASC
                    """
                ).fetchall()
                return [dict(row) for row in rows]

        return await asyncio.to_thread(_get)


async def delete_watch_session(session_id: str) -> None:
    async with db_lock:
        def _delete() -> None:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("DELETE FROM watch_sessions WHERE session_id = ?", (session_id,))
                c.execute("DELETE FROM watch_playlists WHERE session_id = ?", (session_id,))
                conn.commit()
        await asyncio.to_thread(_delete)


async def get_watch_playlist(session_id: str) -> List[Dict[str, Any]]:
    async with db_lock:
        def _get() -> List[Dict[str, Any]]:
            with _connect_database() as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                c.execute(
                    "SELECT video_url, video_title, added_by, order_index FROM watch_playlists WHERE session_id = ? ORDER BY order_index ASC",
                    (session_id,)
                )
                return [dict(row) for row in c.fetchall()]
        return await asyncio.to_thread(_get)


async def add_to_watch_playlist(session_id: str, video_url: str, video_title: str, added_by: str) -> None:
    async with db_lock:
        def _add() -> None:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("SELECT COALESCE(MAX(order_index), 0) FROM watch_playlists WHERE session_id = ?", (session_id,))
                max_idx = c.fetchone()[0]
                
                c.execute(
                    "INSERT OR REPLACE INTO watch_playlists (session_id, video_url, video_title, added_by, order_index) VALUES (?, ?, ?, ?, ?)",
                    (session_id, video_url, video_title, added_by, max_idx + 1)
                )
                conn.commit()
        await asyncio.to_thread(_add)


async def remove_from_watch_playlist(session_id: str, video_url: str) -> None:
    async with db_lock:
        def _remove() -> None:
            with _connect_database() as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("DELETE FROM watch_playlists WHERE session_id = ? AND video_url = ?", (session_id, video_url))
                conn.commit()
        await asyncio.to_thread(_remove)
