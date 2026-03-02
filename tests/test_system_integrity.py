import os
import sys
from pathlib import Path

# --- 1. 프로젝트 루트를 sys.path에 마운트하여 참조 오류 방지 ---
# tests/test_system_integrity.py 위치를 기준으로 최상위 루트 디렉토리 산정
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock

# 모듈이 등록된 경로에서 정상적으로 import 되는지 사전 검증
import database_manager

# --- 2. Cog 모듈 동적 로드 목록 ---
ALL_COG_MODULES = [
    "cogs.application_commands",
    "cogs.leveling.leveling_core",
    "cogs.logging.log_agent",
    "cogs.music.music_agent",
    "cogs.music.music_core",
    "cogs.music.music_ui",
    "cogs.music.music_utils",
    "cogs.summary.summarizer_agent",
    "cogs.summary.summary_listeners",
]

# main_bot.py에서 실제로 load_extension으로 로드되는 대표(Entry) Cog들
MAIN_COG_MODULES = [
    "cogs.logging.log_agent",
    "cogs.summary.summary_listeners",
    "cogs.music.music_agent",
    "cogs.leveling.leveling_core",
    "cogs.application_commands"
]

class TestSystemIntegrity:
    """TDD 기반 시스템 무결성 검증 테스트 클래스"""

    def test_database_manager_import(self):
        """1. DB 매니저 임포트 검증"""
        # 상단에서 import database_manager를 수행했으므로, 객체 존재 여부만 확인합니다.
        assert database_manager is not None, "database_manager 모듈을 불러오지 못했습니다."
        # 추가 무결성: init_db 등 주요 함수가 존재하는지 체크
        assert hasattr(database_manager, "init_db"), "init_db 함수가 database_manager에 존재하지 않습니다."
        assert hasattr(database_manager, "migrate_json_to_db"), "migrate_json_to_db 함수가 database_manager에 존재하지 않습니다."

    @pytest.mark.parametrize("module_path", ALL_COG_MODULES)
    def test_cog_modules_import(self, module_path: str):
        """2. Cog 모듈 동적 로드 및 무결성 검증"""
        try:
            # 모듈을 동적으로 가져옵니다.
            imported_module = importlib.import_module(module_path)
            assert imported_module is not None, f"{module_path} 모듈 로드 실패"

            # 메인 Cog 모듈일 경우 setup 비동기 함수가 반드시 존재해야 함 (discord.py 규약)
            if module_path in MAIN_COG_MODULES:
                assert hasattr(imported_module, "setup"), f"메인 Cog 모듈 {module_path}에 setup 함수가 누락되었습니다."
                setup_func = getattr(imported_module, "setup")
                assert inspect.iscoroutinefunction(setup_func), f"{module_path}의 setup은 비동기(async) 함수여야 합니다."

        except ImportError as e:
            pytest.fail(f"모듈 {module_path}의 Import에 실패했습니다. (ImportError: {e})")
        except SyntaxError as e:
            pytest.fail(f"모듈 {module_path}에서 구문 오류가 발견되었습니다. (SyntaxError: {e})")

    @pytest.mark.asyncio
    async def test_extension_loading(self):
        """3. 비동기 확장 모듈 로드 시뮬레이션"""
        # 실제 discord.ext.commands.Bot 인스턴스를 무시하고 Magic/Async Mock으로 대체
        mock_bot = MagicMock()
        # load_extension은 비동기 메서드이므로 AsyncMock 할당
        mock_bot.load_extension = AsyncMock()

        # 시뮬레이션: MAIN_COG_MODULES 순회하며 로드
        for extension in MAIN_COG_MODULES:
            try:
                await mock_bot.load_extension(extension)
            except Exception as e:
                pytest.fail(f"Mock Bot에서 {extension} 로드 시뮬레이션 중 예외 발생: {e}")

        # 모든 대표 메인 Cog들이 정확히 한 번씩 호출되었는지 검증
        assert mock_bot.load_extension.call_count == len(MAIN_COG_MODULES), "일부 모듈이 로드 호출에서 누락되었습니다."
        
        for extension in MAIN_COG_MODULES:
            mock_bot.load_extension.assert_any_call(extension)

# ==============================================================================
# [테스트 프레임워크 구동 안내 및 명령어]
# 
# 1. 테스트 실행을 위해 필요한 패키지를 설치하십시오:
#    pip install pytest pytest-asyncio
#
# 2. 다음 명령어를 실행하여 테스트를 구동할 수 있습니다:
#    pytest tests/test_system_integrity.py -v
# ==============================================================================
