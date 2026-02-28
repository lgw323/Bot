import sqlite3
import json
import os
import logging
import asyncio

logger = logging.getLogger("DatabaseManager")
DB_PATH = "data/bot_database.db"

# 기존 JSON 경로
FAVORITES_FILE = "data/favorites.json"
MUSIC_SETTINGS_FILE = "data/music_settings.json"

db_lock = asyncio.Lock()

def init_db():
    os.makedirs("data", exist_ok=True)
    
    # 0. 백업 기반 자동 복구 (Main DB가 없고 SQL 덤프가 있는 경우)
    sql_backup_path = "data/database_backup.sql"
    if not os.path.exists(DB_PATH) and os.path.exists(sql_backup_path):
        logger.info(f"Main DB not found. Restoring from {sql_backup_path}...")
        try:
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                with open(sql_backup_path, 'r', encoding='utf-8') as f:
                    sql_script = f.read()
                conn.executescript(sql_script)
                conn.commit()
            logger.info("Database restored successfully from SQL dump.")
        except Exception as e:
            logger.error(f"Failed to restore DB: {e}")

    with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
        c = conn.cursor()
        
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
        
        # [MIGRATION_HOOK]
        migrate_users_schema(conn)
        
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
                PRIMARY KEY(user_id, url),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        
        conn.commit()
    logger.info("Database schemas initialized.")

def migrate_users_schema(conn):
    """
    (1회성 마이그레이션) users 테이블의 PK를 (user_id, guild_id)로 변경합니다.
    성공적으로 수행되면 이 함수를 호출하는 부분 구문([MIGRATION_HOOK]) 전체가 정규식을 통해 자동 삭제(수술용 녹는 실)됩니다.
    """
    c = conn.cursor()
    # Check if migration is needed (if the PK is just user_id)
    c.execute("PRAGMA table_info(users)")
    columns = c.fetchall()
    
    # Pragma table_info returns: cid, name, type, notnull, dflt_value, pk
    pk_count = sum(1 for col in columns if col[5] > 0)
    
    if pk_count > 1:
        # Already migrated. Now let's perform self-deletion of the hook.
        logger.info("Migration already applied. Cleaning up migration hook...")
        _cleanup_migration_hook()
        return

    logger.warning("Starting users table schema migration to support multi-guild...")
    try:
        # Create new table
        c.execute('''
            CREATE TABLE users_new (
                user_id INTEGER,
                guild_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                total_vc_seconds INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')
        
        # Copy data, treating guild_id 0 as potentially needing to be isolated in one server, 
        # but since we don't know which, we just copy it as is. Subsequent interactions will create new rows for other servers.
        c.execute('INSERT INTO users_new SELECT * FROM users')
        
        # Drop old and rename
        c.execute('DROP TABLE users')
        c.execute('ALTER TABLE users_new RENAME TO users')
        
        conn.commit()
        logger.warning("Users table successfully migrated to composite PK!")
        
        # Self-delete the hook
        _cleanup_migration_hook()
        
    except Exception as e:
        logger.error(f"Failed to migrate schema: {e}")
        conn.rollback()

def _cleanup_migration_hook():
    """자신의 파이썬 파일을 읽어서 마이그레이션 훅 부분을 지우고 덮어씁니다."""
    try:
        file_path = os.path.abspath(__file__)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if "# [MIGRATION_HOOK]" in content:
            import re
            # [MIGRATION_HOOK] 라인과 바로 밑에 있는 migrate_users_schema(conn) 라인을 지움
            new_content = re.sub(r'\s*#\s*\[MIGRATION_HOOK\]\s*migrate_users_schema\(conn\)', '', content)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            logger.info("Self-deleting migration hook completed. The code has melted away.")
    except Exception as e:
        logger.error(f"Failed to self-delete migration hook: {e}")

async def backup_database_to_sql():
    """안전하게 현재 SQLite DB를 SQL 덤프 파일로 백업합니다."""
    async with db_lock:
        def _backup():
            sql_backup_path = "data/database_backup.sql"
            try:
                with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                    with open(sql_backup_path, 'w', encoding='utf-8') as f:
                        for line in conn.iterdump():
                            f.write(f'{line}\n')
                logger.info("Database successfully backed up to SQL dump.")
                return True
            except Exception as e:
                logger.error(f"Failed to backup DB to SQL: {e}")
                return False
        return await asyncio.to_thread(_backup)

def migrate_json_to_db():
    with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
        c = conn.cursor()
        
        # Migrate music_settings.json (guild_id)
        if os.path.exists(MUSIC_SETTINGS_FILE):
            logger.info("Migrating music_settings.json...")
            try:
                with open(MUSIC_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings_data = json.load(f)
                    
                for guild_id_str, data in settings_data.items():
                    guild_id = int(guild_id_str)
                    volume = data.get("volume", 1.0)
                    c.execute("INSERT OR IGNORE INTO music_settings (guild_id, volume) VALUES (?, ?)", (guild_id, volume))
                    c.execute("UPDATE music_settings SET volume = ? WHERE guild_id = ?", (volume, guild_id))
                    
                    play_counts = data.get("play_counts", {})
                    for url, info in play_counts.items():
                        title = info.get("title", "")
                        count = info.get("count", 1)
                        c.execute("INSERT OR REPLACE INTO music_play_counts (guild_id, url, title, play_count) VALUES (?, ?, ?, ?)",
                                  (guild_id, url, title, count))
                
                logger.info("music_settings.json migrated.")
                os.rename(MUSIC_SETTINGS_FILE, MUSIC_SETTINGS_FILE + ".bak")
            except Exception as e:
                logger.error(f"Error migrating music_settings: {e}")

        # Migrate favorites.json (user_id)
        if os.path.exists(FAVORITES_FILE):
            logger.info("Migrating favorites.json...")
            try:
                with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                    fav_data = json.load(f)
                    
                for user_id_str, data in fav_data.items():
                    if user_id_str == "_guild_settings":
                        continue
                    user_id = int(user_id_str)
                    
                    # Ensure user exists in users table
                    c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, 0))
                    
                    for song in data:
                        title = song.get("title", "")
                        url = song.get("url", "")
                        c.execute("INSERT OR IGNORE INTO favorites (user_id, url, title) VALUES (?, ?, ?)",
                                  (user_id, url, title))
                
                logger.info("favorites.json migrated.")
                os.rename(FAVORITES_FILE, FAVORITES_FILE + ".bak")
            except Exception as e:
                logger.error(f"Error migrating favorites: {e}")

        conn.commit()

# 비동기 DB 조회/조작 유틸 함수
async def get_favorites():
    async with db_lock:
        def _get():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT user_id, url, title FROM favorites")
                res = {}
                for row in c.fetchall():
                    uid = str(row['user_id'])
                    if uid not in res:
                        res[uid] = []
                    res[uid].append({"url": row['url'], "title": row['title']})
                return res
        return await asyncio.to_thread(_get)

async def add_favorite(user_id: int, url: str, title: str):
    async with db_lock:
        def _add():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, 0))
                c.execute("INSERT OR REPLACE INTO favorites (user_id, url, title) VALUES (?, ?, ?)", (user_id, url, title))
                conn.commit()
        await asyncio.to_thread(_add)

async def remove_favorites(user_id: int, urls: list[str]) -> int:
    async with db_lock:
        def _remove():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                c = conn.cursor()
                deleted_count = 0
                for url in urls:
                    c.execute("DELETE FROM favorites WHERE user_id = ? AND url = ?", (user_id, url))
                    deleted_count += c.rowcount
                conn.commit()
                return deleted_count
        return await asyncio.to_thread(_remove)

async def get_music_settings():
    async with db_lock:
        def _get():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                res = {}
                c.execute("SELECT guild_id, volume FROM music_settings")
                for row in c.fetchall():
                    gid = str(row['guild_id'])
                    if gid not in res:
                        res[gid] = {"play_counts": {}}
                    res[gid]["volume"] = row['volume']
                
                c.execute("SELECT guild_id, url, title, play_count FROM music_play_counts")
                for row in c.fetchall():
                    gid = str(row['guild_id'])
                    if gid not in res:
                        res[gid] = {"volume": 1.0, "play_counts": {}}
                    if "play_counts" not in res[gid]:
                        res[gid]["play_counts"] = {}
                    res[gid]["play_counts"][row['url']] = {"title": row['title'], "count": row['play_count']}
                return res
        return await asyncio.to_thread(_get)

async def update_music_volume(guild_id: int, volume: float):
    async with db_lock:
        def _update():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO music_settings (guild_id, volume) VALUES (?, ?)", (guild_id, volume))
                c.execute("UPDATE music_settings SET volume = ? WHERE guild_id = ?", (volume, guild_id))
                conn.commit()
        await asyncio.to_thread(_update)

async def increment_play_count_db(guild_id: int, url: str, title: str):
    async with db_lock:
        def _update():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO music_play_counts (guild_id, url, title, play_count) VALUES (?, ?, ?, 0)", (guild_id, url, title))
                c.execute("UPDATE music_play_counts SET play_count = play_count + 1, title = ? WHERE guild_id = ? AND url = ?", (title, guild_id, url))
                
                c.execute("SELECT url FROM music_play_counts WHERE guild_id = ? ORDER BY play_count DESC LIMIT -1 OFFSET 50", (guild_id,))
                to_delete = [r[0] for r in c.fetchall()]
                for del_url in to_delete:
                    c.execute("DELETE FROM music_play_counts WHERE guild_id = ? AND url = ?", (guild_id, del_url))
                conn.commit()
        await asyncio.to_thread(_update)

async def get_top_played_songs_db(guild_id: int, limit: int = 5):
    async with db_lock:
        def _get():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT url, title, play_count as count FROM music_play_counts WHERE guild_id = ? ORDER BY play_count DESC LIMIT ?", (guild_id, limit))
                return [dict(row) for row in c.fetchall()]
        return await asyncio.to_thread(_get)

# ==========================================
# 레벨링 영역 DB 함수 (Users 테이블)
# ==========================================

async def get_user_data(user_id: int, guild_id: int):
    async with db_lock:
        def _get():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT user_id, guild_id, xp, level, total_vc_seconds FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
                row = c.fetchone()
                # 기존 마이그레이션 유저(0번 길드) 폴백 매커니즘: 만약 현재 서버 기록은 없는데 0번 서버 기록이 있다면 그걸로 시작
                if not row:
                    c.execute("SELECT user_id, guild_id, xp, level, total_vc_seconds FROM users WHERE user_id = ? AND guild_id = ?", (user_id, 0))
                    row = c.fetchone()
                return dict(row) if row else None
        return await asyncio.to_thread(_get)

async def update_user_xp(user_id: int, guild_id: int, xp_added: int, vc_sec_added: int = 0, new_level: int = None):
    async with db_lock:
        def _update():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                c = conn.cursor()
                
                # 먼저 데이터가 있는지 검사 (0번 길드 폴백 처리 포함)
                c.execute("SELECT xp, level, total_vc_seconds FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
                row = c.fetchone()
                
                if row is None:
                    # 현재 길드에 데이터가 없으면 0번 길드에서 데이터를 끌어오는지 확인
                    c.execute("SELECT xp, level, total_vc_seconds FROM users WHERE user_id = ? AND guild_id = ?", (user_id, 0))
                    old_row = c.fetchone()
                    if old_row:
                        # 0번 길드 데이터를 현재 길드로 이전(복사 또는 이동). 여기서는 복사해서 새로 시작.
                        base_xp, base_lvl, base_vc = old_row[0], old_row[1], old_row[2]
                        # 사실상 0번 길드를 이 서버로 귀속시키기 위해 0번을 삭제하고 현재 길드로 UPDATE 하는 것이 깔끔합니다. 
                        # 하지만 다른 서버에서도 쓸 수 있으므로 COPY 후 새로 더해줍니다.
                        c.execute("INSERT OR IGNORE INTO users (user_id, guild_id, xp, level, total_vc_seconds) VALUES (?, ?, ?, ?, ?)",
                                  (user_id, guild_id, base_xp, base_lvl, base_vc))
                    else:
                        c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))

                if new_level is not None:
                    c.execute("UPDATE users SET xp = xp + ?, total_vc_seconds = total_vc_seconds + ?, level = ? WHERE user_id = ? AND guild_id = ?",
                              (xp_added, vc_sec_added, new_level, user_id, guild_id))
                else:
                    c.execute("UPDATE users SET xp = xp + ?, total_vc_seconds = total_vc_seconds + ? WHERE user_id = ? AND guild_id = ?",
                              (xp_added, vc_sec_added, user_id, guild_id))
                conn.commit()
        await asyncio.to_thread(_update)

async def get_top_users(guild_id: int, limit: int = 10):
    async with db_lock:
        def _get():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                
                # 메인 서버(guild_id)와 과거 기록 보관소(guild_id=0)의 데이터를 합치되,
                # 동일 유저라면 경험치가 더 높은 쪽의 레벨과 경험치를 최종 랭킹 산정에 사용하도록 합니다.
                # 이렇게 하면 아직 채팅을 안 쳐서 0번에 머물러있는 사람들도 랭킹에 합류할 수 있습니다.
                c.execute('''
                    SELECT user_id, MAX(xp) as xp, MAX(level) as level
                    FROM users 
                    WHERE guild_id = ? OR guild_id = 0
                    GROUP BY user_id
                    ORDER BY xp DESC
                    LIMIT ?
                ''', (guild_id, limit))
                
                rows = [dict(row) for row in c.fetchall()]
                return rows
        return await asyncio.to_thread(_get)
