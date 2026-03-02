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
         patch("database_manager.SQL_BACKUP_PATH", temp_backup_path):
        
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
        """SQL 덤프 백업 기능이 정상적으로 파일을 생성하는지 검증"""
        # 임의의 데이터 생성
        await database_manager.update_music_volume(111, 0.5)
        
        success = await database_manager.backup_database_to_sql()
        assert success is True
        assert temp_backup_path.exists()
        
        # 덤프 파일 내에 데이터가 존재하는지 확인
        with open(temp_backup_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "CREATE TABLE" in content
            assert "111" in content
            assert "0.5" in content

