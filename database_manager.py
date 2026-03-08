import sqlite3
import json
import logging
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

logger: logging.Logger = logging.getLogger("DatabaseManager")

# 현재 스크립트 위치 기준으로 절대 경로 설정
BASE_DIR: Path = Path(__file__).parent
DATA_DIR: Path = BASE_DIR / "data"

DB_PATH: Path = DATA_DIR / "bot_database.db"
SQL_BACKUP_PATH: Path = DATA_DIR / "database_backup.sql"

# 기존 JSON 경로
FAVORITES_FILE: Path = DATA_DIR / "favorites.json"
MUSIC_SETTINGS_FILE: Path = DATA_DIR / "music_settings.json"

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
            logger.warning("DB_ENCRYPTION_KEY not found in environment variables. Database backups will NOT be encrypted.")
            return None
    return _cipher_suite

def encode_data(text: str) -> str:
    """텍스트를 암호화하여 Hex 변환 문자열 또는 urlsafe_b64 문자열로 리턴합니다."""
    cipher = get_cipher()
    if cipher and text:
        return cipher.encrypt(text.encode('utf-8')).decode('utf-8')
    return text

def decode_data(encrypted_text: str) -> str:
    """암호화된 텍스트를 복호화하여 원문으로 리턴합니다."""
    cipher = get_cipher()
    if cipher and encrypted_text:
        try:
            return cipher.decrypt(encrypted_text.encode('utf-8')).decode('utf-8')
        except InvalidToken:
            # 암호화되지 않은 평문이거나 키가 바뀐 경우 원문 그대로 반환 시도
            return encrypted_text
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_text
    return encrypted_text


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # 0. 백업 기반 자동 복구 (Main DB가 없고 SQL 덤프가 있는 경우)
    if not DB_PATH.exists() and SQL_BACKUP_PATH.exists():
        logger.info(f"Main DB not found. Restoring from {SQL_BACKUP_PATH}...")
        try:
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
                with open(SQL_BACKUP_PATH, 'r', encoding='utf-8') as f:
                    # SQL 덤프 파일 내의 암호화된 데이터를 복호화하여 로드
                    sql_script_lines = []
                    for line in f:
                        # INSERT INTO favorites VALUES(user_id, 'enc_url', 'enc_title'); 의 형태이거나
                        # INSERT INTO music_play_counts VALUES(guild_id, 'enc_url', 'enc_title', play_count);
                        if line.startswith("INSERT INTO \"favorites\" VALUES("):
                            parts = line.split("VALUES(", 1)
                            if len(parts) == 2:
                                value_part = parts[1].rsplit(");", 1)[0]
                                # SQLite 덤프는 문자열을 '' 로 감쌈
                                try:
                                    import ast
                                    # 파이썬 튜플 형태로 파싱 후 복호화 시도
                                    val_tuple = ast.literal_eval("(" + value_part + ")")
                                    if len(val_tuple) == 3:
                                        user_id, enc_url, enc_title = val_tuple
                                        dec_url = decode_data(enc_url)
                                        dec_title = decode_data(enc_title)
                                        
                                        # '' 안의 따옴표 이스케이프 지원용 단순화
                                        dec_url_str = str(dec_url).replace("'", "''")
                                        dec_title_str = str(dec_title).replace("'", "''")
                                        
                                        line = f"INSERT INTO \"favorites\" VALUES({user_id},'{dec_url_str}','{dec_title_str}');\n"
                                except Exception as e:
                                    logger.error(f"Failed to decrypt favorites backup line: {e}")
                                    
                        elif line.startswith("INSERT INTO \"music_play_counts\" VALUES("):
                            parts = line.split("VALUES(", 1)
                            if len(parts) == 2:
                                value_part = parts[1].rsplit(");", 1)[0]
                                try:
                                    import ast
                                    val_tuple = ast.literal_eval("(" + value_part + ")")
                                    if len(val_tuple) == 4:
                                        guild_id, enc_url, enc_title, play_count = val_tuple
                                        dec_url = decode_data(enc_url)
                                        dec_title = decode_data(enc_title)
                                        
                                        dec_url_str = str(dec_url).replace("'", "''")
                                        dec_title_str = str(dec_title).replace("'", "''")
                                        
                                        line = f"INSERT INTO \"music_play_counts\" VALUES({guild_id},'{dec_url_str}','{dec_title_str}',{play_count});\n"
                                except Exception as e:
                                    logger.error(f"Failed to decrypt play counts backup line: {e}")

                        sql_script_lines.append(line)
                    
                    sql_script = "".join(sql_script_lines)
                    
                conn.executescript(sql_script)
                conn.commit()
            logger.info("Database restored successfully from SQL dump.")
        except Exception as e:
            logger.error(f"Failed to restore DB: {e}", exc_info=True)

    with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
        c: sqlite3.Cursor = conn.cursor()
        
        # 1. users
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                guild_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                total_vc_seconds INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')
        
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
        
        conn.commit()
    logger.info("Database schemas initialized.")


async def backup_database_to_sql() -> bool:
    """안전하게 현재 SQLite DB를 SQL 덤프 파일로 백업합니다. 이때 지정된 테이블의 컬럼은 암호화합니다."""
    async with db_lock:
        def _backup() -> bool:
            try:
                with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
                    with open(SQL_BACKUP_PATH, 'w', encoding='utf-8') as f:
                        # iterdump()를 가로채어 특정 INSERT 문일 경우 암호화 수행
                        for line in conn.iterdump():
                            # favorites 테이블의 url, title 필드 암호화
                            if line.startswith("INSERT INTO \"favorites\" VALUES("):
                                try:
                                    parts = line.split("VALUES(", 1)
                                    if len(parts) == 2:
                                        value_part = parts[1].rsplit(");", 1)[0]
                                        
                                        import ast
                                        val_tuple = ast.literal_eval("(" + value_part + ")")
                                        if len(val_tuple) == 3:
                                            user_id, url, title = val_tuple
                                            enc_url = encode_data(str(url))
                                            enc_title = encode_data(str(title))
                                            line = f"INSERT INTO \"favorites\" VALUES({user_id},'{enc_url}','{enc_title}');"
                                except Exception as e:
                                    logger.error(f"Failed to encrypt favorites backup line: {e}")

                            # music_play_counts 테이블의 url, title 필드 암호화
                            elif line.startswith("INSERT INTO \"music_play_counts\" VALUES("):
                                try:
                                    parts = line.split("VALUES(", 1)
                                    if len(parts) == 2:
                                        value_part = parts[1].rsplit(");", 1)[0]
                                        
                                        import ast
                                        val_tuple = ast.literal_eval("(" + value_part + ")")
                                        if len(val_tuple) == 4:
                                            guild_id, url, title, play_count = val_tuple
                                            enc_url = encode_data(str(url))
                                            enc_title = encode_data(str(title))
                                            line = f"INSERT INTO \"music_play_counts\" VALUES({guild_id},'{enc_url}','{enc_title}',{play_count});"
                                except Exception as e:
                                    logger.error(f"Failed to encrypt play counts backup line: {e}")
                            
                            f.write(f'{line}\n')
                logger.info("Database successfully backed up to SQL dump.")
                return True
            except Exception as e:
                logger.error(f"Failed to backup DB to SQL: {e}", exc_info=True)
                return False
        return await asyncio.to_thread(_backup)


def migrate_json_to_db() -> None:
    with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
        c: sqlite3.Cursor = conn.cursor()
        
        # Migrate music_settings.json (guild_id)
        if MUSIC_SETTINGS_FILE.exists():
            logger.info("Migrating music_settings.json...")
            try:
                with open(MUSIC_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings_data: Dict[str, Any] = json.load(f)
                    
                for guild_id_str, data in settings_data.items():
                    guild_id: int = int(guild_id_str)
                    volume: float = data.get("volume", 1.0)
                    c.execute("INSERT OR IGNORE INTO music_settings (guild_id, volume) VALUES (?, ?)", (guild_id, volume))
                    c.execute("UPDATE music_settings SET volume = ? WHERE guild_id = ?", (volume, guild_id))
                    
                    play_counts: Dict[str, Any] = data.get("play_counts", {})
                    for url, info in play_counts.items():
                        title: str = info.get("title", "")
                        count: int = info.get("count", 1)
                        c.execute("INSERT OR REPLACE INTO music_play_counts (guild_id, url, title, play_count) VALUES (?, ?, ?, ?)",
                                  (guild_id, url, title, count))
                
                logger.info("music_settings.json migrated.")
                MUSIC_SETTINGS_FILE.rename(MUSIC_SETTINGS_FILE.with_suffix(".json.bak"))
            except Exception as e:
                logger.error(f"Error migrating music_settings: {e}", exc_info=True)

        # Migrate favorites.json (user_id)
        if FAVORITES_FILE.exists():
            logger.info("Migrating favorites.json...")
            try:
                with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                    fav_data: Dict[str, Any] = json.load(f)
                    
                for user_id_str, data in fav_data.items():
                    if user_id_str == "_guild_settings":
                        continue
                    user_id: int = int(user_id_str)
                    
                    # Ensure user exists in users table
                    c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, 0))
                    
                    for song in data:
                        title: str = song.get("title", "")
                        url: str = song.get("url", "")
                        c.execute("INSERT OR IGNORE INTO favorites (user_id, url, title) VALUES (?, ?, ?)",
                                  (user_id, url, title))
                
                logger.info("favorites.json migrated.")
                FAVORITES_FILE.rename(FAVORITES_FILE.with_suffix(".json.bak"))
            except Exception as e:
                logger.error(f"Error migrating favorites: {e}", exc_info=True)

        conn.commit()


# 비동기 DB 조회/조작 유틸 함수
async def get_favorites() -> Dict[str, List[Dict[str, str]]]:
    async with db_lock:
        def _get() -> Dict[str, List[Dict[str, str]]]:
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
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
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, 0))
                c.execute("INSERT OR REPLACE INTO favorites (user_id, url, title) VALUES (?, ?, ?)", (user_id, url, title))
                conn.commit()
        await asyncio.to_thread(_add)


async def remove_favorites(user_id: int, urls: List[str]) -> int:
    async with db_lock:
        def _remove() -> int:
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
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
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
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
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
                c: sqlite3.Cursor = conn.cursor()
                c.execute("INSERT OR IGNORE INTO music_settings (guild_id, volume) VALUES (?, ?)", (guild_id, volume))
                c.execute("UPDATE music_settings SET volume = ? WHERE guild_id = ?", (volume, guild_id))
                conn.commit()
        await asyncio.to_thread(_update)


async def increment_play_count_db(guild_id: int, url: str, title: str) -> None:
    async with db_lock:
        def _update() -> None:
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
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
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
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
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                c.execute("SELECT user_id, guild_id, xp, level, total_vc_seconds FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
                row = c.fetchone()
                return dict(row) if row else None
        return await asyncio.to_thread(_get)


async def update_user_xp(user_id: int, guild_id: int, xp_added: int, vc_sec_added: int = 0, new_level: Optional[int] = None) -> None:
    async with db_lock:
        def _update() -> None:
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
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


async def get_top_users(guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    async with db_lock:
        def _get() -> List[Dict[str, Any]]:
            with sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False) as conn:
                conn.row_factory = sqlite3.Row
                c: sqlite3.Cursor = conn.cursor()
                
                # 순수하게 현재 서버(guild_id)의 데이터만 가져와 랭킹을 산정합니다.
                c.execute('''
                    SELECT user_id, xp, level
                    FROM users 
                    WHERE guild_id = ?
                    ORDER BY xp DESC
                    LIMIT ?
                ''', (guild_id, limit))
                
                rows: List[Dict[str, Any]] = [dict(row) for row in c.fetchall()]
                return rows
        return await asyncio.to_thread(_get)
