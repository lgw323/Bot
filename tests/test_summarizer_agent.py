import pytest
from datetime import datetime, timezone
from cogs.summary.summarizer_agent import (
    count_tokens,
    to_local_time,
    format_message,
    parse_summary_to_structured_data,
    _build_summary_prompt
)

def test_count_tokens() -> None:
    # 빈 문자열의 경우 0 토큰 반환이어야 하지만 내부 로직상 안전마진 없이 바로 0 리턴
    assert count_tokens("") == 0
    # 영문/숫자 (0.5 토큰) + 여백 5
    assert count_tokens("Hello") == int(5 * 0.5) + 5
    # 한글 (2.5 토큰) + 여백 5
    assert count_tokens("안녕") == int(2 * 2.5) + 5

def test_to_local_time() -> None:
    utc_dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    # TIMEZONE_OFFSET_HOURS is set to 9 hours via tests or env assuming default
    import cogs.summary.summarizer_agent as core
    core.TIMEZONE_OFFSET_HOURS = 9
    local_dt = to_local_time(utc_dt)
    assert local_dt.hour == 9

def test_format_message() -> None:
    import cogs.summary.summarizer_agent as core
    core.TIMEZONE_OFFSET_HOURS = 9
    dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    log_tuple = (dt, 111, 222, "DrBear", "Hello there!")
    formatted = format_message(log_tuple)
    assert "[2025-01-01 09:00:00][DrBear]: Hello there!" == formatted

def test_parse_summary_to_structured_data() -> None:
    fake_response = """
[주제-1] 시스템 구조 개선
논의 시간대: 14:00 ~ 14:30
주요 참여자: DrBear, Alice
핵심 키워드: 리팩토링, 최적화
요약:
- 핵심 요지: TDD를 도입해야 한다.
- 배경/맥락: 기존 코드가 너무 복잡함.
- 세부 내용: pytest를 사용하여 각 코그별로...
---
[전체 대화 개요]
시스템 구조 전반에 걸친 개선 방안이 논의되었습니다.
"""
    data = parse_summary_to_structured_data(fake_response)
    assert len(data['topics']) == 1
    assert data['topics'][0]['title'] == '시스템 구조 개선'
    assert data['topics'][0]['participants'] == 'DrBear, Alice'
    assert data['topics'][0]['main_point'] == 'TDD를 도입해야 한다.'
    assert data['overall_summary'] == '시스템 구조 전반에 걸친 개선 방안이 논의되었습니다.'

def test_build_summary_prompt() -> None:
    prompt = _build_summary_prompt("Dummy Logs", "Please be polite.")
    assert "Dummy Logs" in prompt
    assert "Please be polite." in prompt
