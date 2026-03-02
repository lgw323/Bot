import pytest
import discord
from unittest.mock import AsyncMock, patch, MagicMock

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# cogs.leveling.leveling_core 모듈을 임포트합니다.
from cogs.leveling.leveling_core import LevelingCog, calculate_jamo_length, get_required_xp

class TestLevelingCore:

    def test_calculate_jamo_length(self):
        """한글 자모 길이 산정 알고리즘 무결성 검증"""
        # "안녕" -> '안'(ㅇ,ㅏ,ㄴ) = 3개, '녕'(ㄴ,ㅕ,ㅇ) = 3개 => 6개
        assert calculate_jamo_length("안녕") == 6
        
        # "가나다" -> '가'(ㄱ,ㅏ)=2, '나'(ㄴ,ㅏ)=2, '다'(ㄷ,ㅏ)=2 => 6개
        assert calculate_jamo_length("가나다") == 6
        
        # 영어, 숫자 처리 -> 영문 알파벳/숫자는 1자당 1개 취급
        assert calculate_jamo_length("hello 123") == 8 # h,e,l,l,o,1,2,3 (공백 무시)
        
        # 특수문자나 띄어쓰기는 공백만 무시하고 카운트 1개로 계산
        assert calculate_jamo_length("!@#") == 3

    def test_get_required_xp(self):
        """레벨별 필수 경험치 커브 무결성 검증"""
        assert get_required_xp(1) == int(100 * (1 ** 1.5)) # 100
        assert get_required_xp(2) == int(100 * (2 ** 1.5)) # 282
        assert get_required_xp(10) == int(100 * (10 ** 1.5)) # 3162

    @pytest.mark.asyncio
    async def test_assign_role_by_level(self):
        """레벨에 따른 역할 승급 확인 (Mock 처리)"""
        # Mock 봇 환경 설정
        mock_bot = MagicMock()
        cog = LevelingCog(mock_bot)
        
        # Mock Member, Roles 설정
        mock_member = AsyncMock(spec=discord.Member)
        
        # 역할(Role) 모의 데이터 생성
        role_lv1 = MagicMock(spec=discord.Role, name="Lv.1 Role")
        role_lv1.name = "Lv.1 Beginner"
        
        role_lv10 = MagicMock(spec=discord.Role, name="Lv.10 Role")
        role_lv10.name = "Lv.10 Pro"
        
        role_admin = MagicMock(spec=discord.Role, name="Admin")
        role_admin.name = "Admin Role"
        
        mock_guild = MagicMock()
        mock_guild.roles = [role_admin, role_lv1, role_lv10]
        
        mock_guild.me.guild_permissions.manage_roles = True
        mock_member.guild = mock_guild
        # 멤버가 현재 가지고 있는 역할 리스트
        mock_member.roles = [role_lv1]

        # 테스트 1: 레벨 12에 도달했을 때 (Lv.10 역할이 적용되어야 함)
        await cog.assign_role_by_level(mock_member, 12)
        
        # 기존 역할 제거 및 새 역할 부여가 호출되었는지 검증
        mock_member.remove_roles.assert_called_once_with(role_lv1, reason="레벨업(12)으로 인한 기존 역할 해제")
        mock_member.add_roles.assert_called_once_with(role_lv10, reason="레벨업 달성 (Lv.12)")

    @pytest.mark.asyncio
    @patch("cogs.leveling.leveling_core.get_user_data")
    @patch("cogs.leveling.leveling_core.update_user_xp")
    async def test_on_message_xp_gain(self, mock_update_xp, mock_get_user):
        """on_message 발생 시 XP 연산 및 DB 갱신 프로세스 검증"""
        mock_bot = MagicMock()
        cog = LevelingCog(mock_bot)
        
        mock_message = MagicMock(spec=discord.Message)
        mock_message.author = MagicMock(spec=discord.Member)
        mock_message.author.bot = False
        mock_message.author.id = 111
        mock_message.guild = MagicMock()
        mock_message.guild.id = 222
        
        mock_message.content = "안녕하세요" # 3타+3타+2타+2타+2타 = 12
        expected_xp = 12
        
        # 사용자가 이미 Lv.1이고 XP가 90이라고 가정 (다음 레벨 조건 미충족)
        mock_get_user.return_value = {"level": 1, "xp": 90}
        
        await cog.on_message(mock_message)
        
        # XP 업데이트 함수가 올바른 추가분과 함께 불렸는지 검증 (90 + 12 = 102이므로 레벨 1구간(100)을 넘어 Lv.2가 되어야함)
        mock_update_xp.assert_called_once_with(111, 222, xp_added=expected_xp, new_level=2)
