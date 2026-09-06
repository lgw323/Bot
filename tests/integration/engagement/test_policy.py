from datetime import date, datetime, timezone

import pytest

from cogs.leveling.leveling_core import calculate_jamo_length, get_required_xp
from discordbot.engagement.domain.policy import Progress, birthday_due, notification_date, required_xp, text_xp, valid_birthday


@pytest.mark.parametrize("text", ["", " \n\t", "가", "각", "힣", "abc 123", "🙂!", "안녕 abc!", "ㄱㅏ가", "a\u200b\u00a0"])
def test_text_formula_matches_actual_v1(text):
    assert text_xp(text) == calculate_jamo_length(text)


def test_all_hangul_syllables_and_level_curve_match_v1():
    for point in range(0xAC00, 0xD7A4):
        assert text_xp(chr(point)) == calculate_jamo_length(chr(point))
    for level in range(1, 400):
        assert required_xp(level) == get_required_xp(level)


@pytest.mark.parametrize("seconds,expected", [(0, 0), (59.99, 0), (60, 5), (119.99, 5), (120, 10), (3600, 300)])
def test_completed_minutes(seconds, expected):
    assert Progress(7, seconds).total == 7 + expected


@pytest.mark.parametrize("month,day,valid", [(2, 29, True), (2, 30, False), (2, 31, False), (4, 31, False), (12, 31, True), (0, 1, False), (1, 0, False), (13, 1, False), (True, 1, False)])
def test_calendar(month, day, valid):
    assert valid_birthday(month, day) is valid


@pytest.mark.parametrize("today,expected", [(date(2027, 2, 28), True), (date(2028, 2, 28), False), (date(2028, 2, 29), True), (date(2100, 2, 28), True), (date(2000, 2, 28), False), (date(2027, 3, 1), False)])
def test_feb29_fallback(today, expected):
    assert birthday_due(2, 29, today) is expected
    assert not birthday_due(2, 31, today)


def test_kst_date_and_nine_oclock_year_boundary():
    assert notification_date(datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)) is None
    assert notification_date(datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc)) == date(2027, 1, 1)


def test_scheduler_wakes_exactly_at_nine_when_started_one_second_early():
    from discordbot.engagement.domain.policy import notification_poll_delay
    assert notification_poll_delay(datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)) == 1


@pytest.mark.parametrize("options", [{"birthday_channels": [(100, 1001)]}, {"receipt_capacity": True}, {"request_seconds": float("nan")}, {"voice_capacity": 100001}, {"birthday_channels": ((100, 1), (100, 2))}])
def test_config_rejects_mutable_or_invalid_capacity(options):
    from discordbot.engagement.ports.events import EngagementConfig
    from discordbot.platform.errors import ConfigurationError
    with pytest.raises(ConfigurationError):
        EngagementConfig(42, **options)
