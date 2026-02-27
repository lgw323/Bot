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
                user_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                total_vc_seconds INTEGER DEFAULT 0
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
                PRIMARY KEY(user_id, url),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        
        conn.commit()
    logger.info("Database schemas initialized.")

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

async def get_user_data(user_id: int):
    async with db_lock:
        def _get():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT user_id, guild_id, xp, level, total_vc_seconds FROM users WHERE user_id = ?", (user_id,))
                row = c.fetchone()
                return dict(row) if row else None
        return await asyncio.to_thread(_get)

async def update_user_xp(user_id: int, guild_id: int, xp_added: int, vc_sec_added: int = 0, new_level: int = None):
    async with db_lock:
        def _update():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                c = conn.cursor()
                # 신규 유저는 접속한 서버 기준으로 생성
                c.execute("INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
                if new_level is not None:
                    c.execute("UPDATE users SET xp = xp + ?, total_vc_seconds = total_vc_seconds + ?, level = ? WHERE user_id = ?",
                              (xp_added, vc_sec_added, new_level, user_id))
                else:
                    c.execute("UPDATE users SET xp = xp + ?, total_vc_seconds = total_vc_seconds + ? WHERE user_id = ?",
                              (xp_added, vc_sec_added, user_id))
                conn.commit()
        await asyncio.to_thread(_update)

async def get_top_users(guild_id: int, limit: int = 10):
    async with db_lock:
        def _get():
            with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                # 봇이 속한 서버(guild_id) 내의 유저 랭킹 반환
                c.execute("SELECT user_id, xp, level FROM users WHERE guild_id = ? ORDER BY xp DESC LIMIT ?", (guild_id, limit))
                return [dict(row) for row in c.fetchall()]
        return await asyncio.to_thread(_get)
