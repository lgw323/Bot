import pytest
import sqlite3
import os
import asyncio
from pathlib import Path
from unittest.mock import patch, ANY
from typing import Any, Dict, List

# Add project root to sys.path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 테스트용 환경설정 - 실제 데이터베이스 파일 대신 InMemory를 사용하거나,
# 테스트 전용 파일 경로를 사용하도록 db_lock 및 상수를 패치해야 합니다.
import database_manager

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
         patch("subprocess.run"):
        
        # 테스트 전 DB 초기화 실행 (메모리 누수나 기존 파일 오염 방지)
        database_manager.init_db()
        yield temp_db_path
        # 테스트 종료 후 yield 지점 이하 코드가 실행됩니다. (정리 과정 생략 가능)

class TestDatabaseManager:
    
    def test_init_db_creates_tables(self, setup_database):
        """init_db() 호출 시 스키마 생성 무결성 검증"""
        temp_db_path = setup_database
        
        # 실제 파일이 생성되었는지 확인
        assert temp_db_path.exists()
        
        # 필수 테이블 4개가 생성되었는지 확인
        with sqlite3.connect(temp_db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in c.fetchall()]
            
            assert "users" in tables
            assert "music_settings" in tables
            assert "music_play_counts" in tables
            assert "favorites" in tables

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
    async def test_backup_database_to_sql(self, setup_database, temp_backup_path):
        """SQL 덤프 백업 기능이 정상적으로 파일을 생성하며, 데이터를 난독화하는지 검증"""
        user_id = 999
        guild_id = 111
        url = "https://youtube.com/watch?v=123"
        title = "Super Secret Test Song"
        
        # 임의의 데이터 생성
        await database_manager.update_music_volume(guild_id, 0.5)
        await database_manager.add_favorite(user_id, url, title)
        await database_manager.increment_play_count_db(guild_id, url, title)
        
        # 암호화 키 임시 주입 (테스트 중 키가 없으면 암호화 건너뜀)
        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": "f5iIv-yFsEWQjBfXjS-_of6aiR77NjTEToBhAz6EnZs="}):
            # 내부 cipher 초기화
            database_manager._cipher_suite = None 
            
            success = await database_manager.backup_database_to_sql()
            assert success is True
            assert temp_backup_path.exists()
            
            # 덤프 파일 내에 데이터가 존재하는지, 그리고 원문이 노출되지 않는지 확인
            with open(temp_backup_path, 'r', encoding='utf-8') as f:
                content = f.read()
                assert "CREATE TABLE" in content
                assert str(guild_id) in content
                assert "0.5" in content
                
                # 난독화가 성공했다면 원문 URL이나 타이틀이 SQL 파일에 보이지 않아야 함
                assert "Super Secret Test Song" not in content
                assert "youtube.com/watch" not in content

    @pytest.mark.asyncio
    async def test_restore_from_encrypted_backup(self, setup_database, temp_db_path, temp_backup_path):
        """암호화되어 저장된 SQL 덤프 파일로부터 DB가 원문으로 정상 복구되는지 통합 검증"""
        user_id = 777
        guild_id = 555
        url = "https://youtu.be/abcde"
        title = "Healing Music"
        
        # 1. 원본 데이터 세팅 및 암호화 백업
        await database_manager.add_favorite(user_id, url, title)
        await database_manager.increment_play_count_db(guild_id, url, title)
        
        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": "f5iIv-yFsEWQjBfXjS-_of6aiR77NjTEToBhAz6EnZs="}):
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
        with patch.dict(os.environ, {"DB_ENCRYPTION_KEY": "f5iIv-yFsEWQjBfXjS-_of6aiR77NjTEToBhAz6EnZs="}):
            database_manager._cipher_suite = None
            database_manager.init_db()
            
        assert temp_db_path.exists()
        
        # 4. 복구된 DB의 데이터 무결성 100% 원문 일치 검증
        favs = await database_manager.get_favorites()
        assert str(user_id) in favs
        # 암호문이 아닌 원문이 그대로 들어있어야 함
        assert favs[str(user_id)][0]["title"] == "Healing Music"
        assert favs[str(user_id)][0]["url"] == "https://youtu.be/abcde"
        
        top_songs = await database_manager.get_top_played_songs_db(guild_id)
        assert len(top_songs) > 0
        assert top_songs[0]["title"] == "Healing Music"
        assert top_songs[0]["url"] == "https://youtu.be/abcde"

