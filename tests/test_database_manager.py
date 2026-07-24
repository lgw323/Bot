import pytest
import sqlite3
import os
import asyncio
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

import database_manager

TEST_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
PRIVATE_BACKUP_REMOTE = "https://github.com/lgw323/Bot-Data.git"


def assert_no_backup_temp_files(backup_path):
    temp_pattern = f".{backup_path.stem}.*.tmp"
    assert list(backup_path.parent.glob(temp_pattern)) == []


@pytest.fixture
def temp_db_path(tmp_path):
    """임시 데이터베이스 경로를 생성하는 픽스처"""
    db_file = tmp_path / "test_bot_database.db"
    return db_file

@pytest.fixture
def temp_backup_path(tmp_path):
    return tmp_path / "test_backup.sql"

@pytest.fixture
def setup_database(temp_db_path, temp_backup_path):
    """테스트를 위해 database_manager의 DB 경로를 임시 경로로 패치하고 초기화합니다."""
    with patch("database_manager.DB_PATH", temp_db_path), \
         patch("database_manager.DATA_DIR", temp_db_path.parent), \
         patch("database_manager.SQL_BACKUP_PATH", temp_backup_path), \
         patch("subprocess.run") as mock_run:
        
        # mock_run의 반환값을 수정해서 write_bytes가 에러나지 않게 방어
        mock_run.return_value.stdout = b""
        
        # 테스트 전 DB 초기화 실행 (메모리 누수나 기존 파일 오염 방지)
        database_manager.init_db()
        yield temp_db_path
        database_manager._cipher_suite = None

class TestDatabaseManager:

    def test_import_does_not_replace_global_sqlite_connect(self):
        """DB 설정이 다른 라이브러리의 SQLite 연결까지 바꾸면 안 됩니다."""
        assert sqlite3.connect.__module__ == "_sqlite3"

    def test_init_db_fetches_backup_when_local_data_is_missing(
        self,
        tmp_path,
    ):
        """로컬 데이터가 전혀 없으면 db-backup 브랜치에서 복구를 시도합니다."""
        db_path = tmp_path / "restored_bot_database.db"
        backup_path = tmp_path / "restored_database_backup.sql"
        backup_sql = b"BEGIN TRANSACTION;\nCOMMIT;\n"
        fetch_result = MagicMock(stdout=b"")
        show_result = MagicMock(stdout=backup_sql)

        with patch("database_manager.DB_PATH", db_path), \
             patch("database_manager.DATA_DIR", tmp_path), \
             patch("database_manager.SQL_BACKUP_PATH", backup_path), \
             patch.dict(
                 os.environ,
                 {"DB_BACKUP_REMOTE_URL": PRIVATE_BACKUP_REMOTE},
             ), \
             patch("subprocess.run", side_effect=[fetch_result, show_result]) as mock_run:
            database_manager.init_db()

        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0].args[0] == [
            "git",
            "fetch",
            "--no-tags",
            PRIVATE_BACKUP_REMOTE,
            "db-backup",
        ]
        assert mock_run.call_args_list[1].args[0] == [
            "git", "show", "FETCH_HEAD:data/database_backup.sql"
        ]
        assert backup_path.read_bytes() == backup_sql
        assert db_path.exists()

    def test_init_db_halts_without_private_backup_remote(
        self,
        tmp_path,
    ):
        """별도 백업 주소가 없을 때 공개 코드 저장소로 우회하면 안 됩니다."""
        db_path = tmp_path / "blocked_without_remote.db"
        backup_path = tmp_path / "missing_without_remote.sql"

        with patch("database_manager.DB_PATH", db_path), \
             patch("database_manager.DATA_DIR", tmp_path), \
             patch("database_manager.SQL_BACKUP_PATH", backup_path), \
             patch.dict(os.environ, {}, clear=True), \
             patch("subprocess.run") as mock_run:
            with pytest.raises(SystemExit, match="DB_BACKUP_REMOTE_URL"):
                database_manager.init_db()

        mock_run.assert_not_called()
        assert not db_path.exists()
        assert not backup_path.exists()

    def test_init_db_halts_when_remote_backup_fetch_fails(
        self,
        tmp_path,
    ):
        """현재 안전 정책은 원격 복구 실패 시 빈 운영 DB 생성을 막는 것입니다."""
        db_path = tmp_path / "blocked_bot_database.db"
        backup_path = tmp_path / "missing_database_backup.sql"

        with patch("database_manager.DB_PATH", db_path), \
             patch("database_manager.DATA_DIR", tmp_path), \
             patch("database_manager.SQL_BACKUP_PATH", backup_path), \
             patch.dict(
                 os.environ,
                 {"DB_BACKUP_REMOTE_URL": PRIVATE_BACKUP_REMOTE},
             ), \
             patch("subprocess.run", side_effect=RuntimeError("offline")):
            with pytest.raises(SystemExit, match="Empty DB creation blocked"):
                database_manager.init_db()

        assert not db_path.exists()
        assert not backup_path.exists()

    def test_init_db_halts_when_remote_backup_is_invalid(
        self,
        tmp_path,
    ):
        """손상된 원격 백업으로 빈 운영 DB를 만들면 안 됩니다."""
        db_path = tmp_path / "blocked_invalid_database.db"
        backup_path = tmp_path / "invalid_database_backup.sql"
        fetch_result = MagicMock(stdout=b"")
        show_result = MagicMock(
            stdout=b"BEGIN TRANSACTION;\nNOT VALID SQL;\nCOMMIT;\n"
        )

        with patch("database_manager.DB_PATH", db_path), \
             patch("database_manager.DATA_DIR", tmp_path), \
             patch("database_manager.SQL_BACKUP_PATH", backup_path), \
             patch.dict(
                 os.environ,
                 {"DB_BACKUP_REMOTE_URL": PRIVATE_BACKUP_REMOTE},
             ), \
             patch(
                 "subprocess.run",
                 side_effect=[fetch_result, show_result],
             ):
            with pytest.raises(RuntimeError, match="Failed to restore DB"):
                database_manager.init_db()

        assert not db_path.exists()
        assert backup_path.exists()
    
    def test_init_db_creates_tables(self, setup_database):
        """init_db() 호출 시 스키마 생성 무결성 검증"""
        temp_db_path = setup_database
        
        # 실제 파일이 생성되었는지 확인
        assert temp_db_path.exists()
        
        # 필수 테이블 4개가 생성되었는지 확인
        with database_manager._connect_database(temp_db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in c.fetchall()]
            
            assert "users" in tables
            assert "music_settings" in tables
            assert "music_play_counts" in tables
            assert "favorites" in tables

    def test_sqlite_pragmas_applied(self, setup_database):
        """SQLite WAL 모드 및 성능 최적화 PRAGMA가 데이터베이스 연결에 올바르게 적용되는지 검증"""
        temp_db_path = setup_database
        with database_manager._connect_database(temp_db_path) as conn:
            c = conn.cursor()
            c.execute("PRAGMA journal_mode;")
            journal_mode = c.fetchone()[0]
            assert journal_mode.lower() == "wal"
            
            c.execute("PRAGMA synchronous;")
            synchronous = c.fetchone()[0]
            assert synchronous == 1
            
            c.execute("PRAGMA temp_store;")
            temp_store = c.fetchone()[0]
            assert temp_store == 2

    @pytest.mark.asyncio
    async def test_user_xp_update_and_get(self, setup_database):
        """레벨링 시스템의 XP 업데이트와 조회가 정상 동작하는지 트랜잭션 검증"""
        # User ID, Guild ID
        user_id = 12345
        guild_id = 54321
        
        # 초기 유저 데이터가 없는지 확인
        data_before = await database_manager.get_user_data(user_id, guild_id)
        assert data_before is None
        
        # XP 및 체류시간 업데이트
        await database_manager.update_user_xp(user_id, guild_id, xp_added=150, vc_sec_added=1200, new_level=2)
        
        # 데이터가 정상적으로 INSERT 혹은 UPDATE 되었는지 검증
        data_after = await database_manager.get_user_data(user_id, guild_id)
        assert data_after is not None
        assert data_after["xp"] == 150
        assert data_after["level"] == 2
        assert data_after["total_vc_seconds"] == 1200
        
        # 랭킹 시스템 검증
        top_users = await database_manager.get_top_users(guild_id)
        assert len(top_users) == 1
        assert top_users[0]["user_id"] == user_id
        assert top_users[0]["xp"] == 150
        assert top_users[0]["total_xp"] == 250  # 150 Text XP + (1200 / 60) * 5 Voice XP

    @pytest.mark.asyncio
    async def test_music_settings_and_favorites(self, setup_database):
        """음악 설정, 플레이 횟수, 즐겨찾기 CRUD 트랜잭션 검증"""
        user_id = 999
        guild_id = 888
        url = "https://youtube.com/watch?v=123"
        title = "Test Song"
        
        # 1. Music volume 설정 변경
        await database_manager.update_music_volume(guild_id, 0.75)
        
        # 2. 플레이 횟수 증가
        await database_manager.increment_play_count_db(guild_id, url, title)
        await database_manager.increment_play_count_db(guild_id, url, title) # 2회 재생
        
        # 3. 즐겨찾기 추가
        await database_manager.add_favorite(user_id, url, title)
        
        # 검증
        settings = await database_manager.get_music_settings()
        assert str(guild_id) in settings
        assert settings[str(guild_id)]["volume"] == 0.75
        assert url in settings[str(guild_id)]["play_counts"]
        assert settings[str(guild_id)]["play_counts"][url]["count"] == 2
        
        top_played = await database_manager.get_top_played_songs_db(guild_id)
        assert top_played[0]["url"] == url
        assert top_played[0]["count"] == 2
        
        favorites = await database_manager.get_favorites()
        assert str(user_id) in favorites
        assert any(fav["url"] == url for fav in favorites[str(user_id)])

    @pytest.mark.asyncio
    async def test_favorites_are_shared_by_user_across_guilds(
        self,
        setup_database,
    ):
        """같은 사용자의 즐겨찾기는 서버별 목록으로 분리되지 않습니다."""
        user_id = 4242
        first_guild_id = 100
        second_guild_id = 200
        url = "https://youtube.com/watch?v=global-favorite"

        await database_manager.update_user_xp(
            user_id,
            first_guild_id,
            xp_added=10,
            vc_sec_added=0,
            new_level=1,
        )
        await database_manager.update_user_xp(
            user_id,
            second_guild_id,
            xp_added=20,
            vc_sec_added=0,
            new_level=1,
        )
        await database_manager.add_favorite(user_id, url, "Shared Favorite")

        favorites = await database_manager.get_favorites()

        assert list(favorites) == [str(user_id)]
        assert favorites[str(user_id)] == [
            {"url": url, "title": "Shared Favorite"}
        ]

    @pytest.mark.asyncio
    async def test_backup_database_to_sql(self, setup_database, temp_backup_path):
        """백업 파일 전체가 암호화되고 올바른 키로만 원문을 확인할 수 있어야 합니다."""
        user_id = 999
        guild_id = 111
        url = "https://youtube.com/watch?v=123"
        title = "Super Secret Test Song"
        session_id = "visible-watch-session-marker"
        
        # 임의의 데이터 생성
        await database_manager.update_music_volume(guild_id, 0.5)
        await database_manager.add_favorite(user_id, url, title)
        await database_manager.increment_play_count_db(guild_id, url, title)
        await database_manager.add_watch_session(
            session_id,
            guild_id,
            user_id,
        )
        
        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            database_manager._cipher_suite = None 
            
            success = await database_manager.backup_database_to_sql()
            assert success is True
            assert temp_backup_path.exists()

            content = temp_backup_path.read_bytes()
            assert content.startswith(b"DISCORDBOT_BACKUP_V2\n")
            assert b"CREATE TABLE" not in content
            assert b'Super Secret Test Song' not in content
            assert b'youtube.com/watch' not in content
            assert session_id.encode("utf-8") not in content
            assert b'INSERT INTO "favorites" VALUES(999' not in content

            encrypted_payload = content.split(b"\n", 1)[1]
            decrypted_sql = Fernet(
                TEST_ENCRYPTION_KEY.encode("ascii")
            ).decrypt(encrypted_payload)
            assert b"CREATE TABLE" in decrypted_sql
            assert title.encode("utf-8") in decrypted_sql
            assert session_id.encode("utf-8") in decrypted_sql
            assert_no_backup_temp_files(temp_backup_path)

    @pytest.mark.asyncio
    async def test_backup_without_encryption_key_preserves_previous_backup(
        self,
        setup_database,
        temp_backup_path,
    ):
        """암호화 키가 없으면 평문 백업을 만들거나 정상 백업을 덮어쓰면 안 됩니다."""
        previous_backup = "LAST KNOWN GOOD BACKUP\n"
        temp_backup_path.write_text(previous_backup, encoding="utf-8")

        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": ""}):
            database_manager._cipher_suite = None
            success = await database_manager.backup_database_to_sql()

        assert success is False
        assert temp_backup_path.read_text(encoding="utf-8") == previous_backup
        assert_no_backup_temp_files(temp_backup_path)

    @pytest.mark.asyncio
    async def test_backup_generation_failure_preserves_previous_backup(
        self,
        setup_database,
        temp_backup_path,
    ):
        """SQL 덤프 생성 도중 실패해도 마지막 정상 백업은 유지되어야 합니다."""
        previous_backup = "LAST KNOWN GOOD BACKUP\n"
        temp_backup_path.write_text(previous_backup, encoding="utf-8")
        connection = MagicMock()
        connection.__enter__.return_value.iterdump.side_effect = RuntimeError(
            "dump failed"
        )

        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}), \
             patch("database_manager._connect_database", return_value=connection):
            database_manager._cipher_suite = None
            success = await database_manager.backup_database_to_sql()

        assert success is False
        assert temp_backup_path.read_text(encoding="utf-8") == previous_backup
        assert_no_backup_temp_files(temp_backup_path)

    @pytest.mark.asyncio
    async def test_invalid_sql_dump_preserves_previous_backup(
        self,
        setup_database,
        temp_backup_path,
    ):
        """완성된 덤프가 유효한 SQL이 아니면 기존 백업과 교체하면 안 됩니다."""
        previous_backup = "LAST KNOWN GOOD BACKUP\n"
        temp_backup_path.write_text(previous_backup, encoding="utf-8")
        connection = MagicMock()
        connection.__enter__.return_value.iterdump.return_value = iter(
            ["NOT VALID SQL;"]
        )

        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}), \
             patch("database_manager._connect_database", return_value=connection):
            database_manager._cipher_suite = None
            success = await database_manager.backup_database_to_sql()

        assert success is False
        assert temp_backup_path.read_text(encoding="utf-8") == previous_backup
        assert_no_backup_temp_files(temp_backup_path)

    @pytest.mark.asyncio
    async def test_restore_from_encrypted_backup(self, setup_database, temp_db_path, temp_backup_path):
        """암호화되어 저장된 SQL 덤프 파일로부터 DB가 원문으로 정상 복구되는지 통합 검증"""
        user_id = 777
        guild_id = 555
        url = "https://youtu.be/abcde"
        title = "Friend's Healing Music"
        
        # 1. 원본 데이터 세팅 및 암호화 백업
        await database_manager.add_favorite(user_id, url, title)
        await database_manager.increment_play_count_db(guild_id, url, title)
        
        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            database_manager._cipher_suite = None
            await database_manager.backup_database_to_sql()
        
        # 2. 메인 DB 고의 삭제 (서버 포맷 시뮬레이션)
        # 윈도우 환경 특성상 SQLite connection close가 test 환경에서 즉각 반영되지 않아
        # PermissionError 리턴 가능성이 있으므로 짧게 양보
        await asyncio.sleep(0.1)
        import gc
        gc.collect()
        
        try:
            os.remove(temp_db_path)
        except PermissionError:
            # 윈도우 환경 테스트시 파일이 잠겨 삭제 실패할 경우, 
            # 단순히 데이터를 날리는 쿼리로 대체하여 같은 테스트 목적성을 달성합니다.
            import sqlite3
            with sqlite3.connect(temp_db_path) as conn:
                conn.execute("DELETE FROM favorites")
                conn.execute("DELETE FROM music_play_counts")
                conn.commit()
                
        # 3. DB 초기화 (이 때 SQL 백업본을 감지하고 복구 로직이 돌아가야 함)
        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            database_manager._cipher_suite = None
            database_manager.init_db()
            
        assert temp_db_path.exists()
        
        # 4. 복구된 DB의 데이터 무결성 100% 원문 일치 검증
        favs = await database_manager.get_favorites()
        assert str(user_id) in favs
        # 암호문이 아닌 원문이 그대로 들어있어야 함
        assert favs[str(user_id)][0]["title"] == title
        assert favs[str(user_id)][0]["url"] == url
        
        top_songs = await database_manager.get_top_played_songs_db(guild_id)
        assert len(top_songs) > 0
        assert top_songs[0]["title"] == title
        assert top_songs[0]["url"] == url

    @pytest.mark.asyncio
    async def test_restore_with_wrong_key_does_not_publish_unreadable_database(
        self,
        setup_database,
        temp_db_path,
    ):
        """다른 키로 복구한 암호문을 정상 데이터처럼 운영 DB에 넣으면 안 됩니다."""
        await database_manager.add_favorite(
            123,
            "https://youtu.be/protected",
            "Protected Song",
        )

        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY}):
            database_manager._cipher_suite = None
            assert await database_manager.backup_database_to_sql() is True

        restore_db_path = temp_db_path.with_name("wrong_key_restore.db")
        wrong_key = Fernet.generate_key().decode("ascii")

        with patch("database_manager.DB_PATH", restore_db_path), \
             patch.dict(os.environ, {"DB_ENCRYPTION_KEY": wrong_key}):
            database_manager._cipher_suite = None
            with pytest.raises(RuntimeError, match="Failed to restore DB"):
                database_manager.init_db()

        assert not restore_db_path.exists()

    def test_restore_supports_legacy_field_encrypted_sql_backup(
        self,
        tmp_path,
    ):
        """전환 전에 만든 필드 암호화 SQL도 기존 키로 계속 복구할 수 있어야 합니다."""
        db_path = tmp_path / "legacy_restored.db"
        backup_path = tmp_path / "legacy_backup.sql"
        cipher = Fernet(TEST_ENCRYPTION_KEY.encode("ascii"))
        url = "https://youtu.be/legacy"
        title = "Legacy Friend's Song"
        encrypted_url = cipher.encrypt(url.encode("utf-8")).decode("ascii")
        encrypted_title = cipher.encrypt(title.encode("utf-8")).decode("ascii")
        escaped_encrypted_url = encrypted_url.replace("'", "''")
        escaped_encrypted_title = encrypted_title.replace("'", "''")
        backup_path.write_text(
            "BEGIN TRANSACTION;\n"
            "CREATE TABLE favorites ("
            "user_id INTEGER, url TEXT, title TEXT, "
            "PRIMARY KEY(user_id, url));\n"
            f'INSERT INTO "favorites" VALUES('
            f"777,'{escaped_encrypted_url}','{escaped_encrypted_title}');\n"
            "COMMIT;\n",
            encoding="utf-8",
        )

        with patch("database_manager.DB_PATH", db_path), \
             patch("database_manager.DATA_DIR", tmp_path), \
             patch("database_manager.SQL_BACKUP_PATH", backup_path), \
             patch.dict(
                 os.environ,
                 {"DB_ENCRYPTION_KEY": TEST_ENCRYPTION_KEY},
             ):
            database_manager._cipher_suite = None
            database_manager.init_db()

        with database_manager._connect_database(db_path) as conn:
            row = conn.execute(
                "SELECT url, title FROM favorites WHERE user_id = 777"
            ).fetchone()

        assert row == (url, title)

