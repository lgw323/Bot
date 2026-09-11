from types import SimpleNamespace
from unittest.mock import MagicMock

import discord
import pytest

from cogs.logging.log_agent import RestartControlView, WatchSessionControlView
from cogs.music.music_ui import (
    ConfirmClearView,
    FavoritesView,
    MusicPlayerView,
    QueueManagementView,
    SearchSelect,
    SearchSongModal,
)
from cogs.music.music_utils import LoopMode
from cogs.summary.summary_listeners import AdvancedSummaryModal, SummaryView
from cogs.watch_together.watch_agent import WatchTogetherJoinView


def _song(index: int) -> SimpleNamespace:
    return SimpleNamespace(
        title=f"Song {index}",
        webpage_url=f"https://example.invalid/{index}",
    )


def test_f011_f013_f022_fr011_fr012_fr016_preserve_music_component_inventory() -> None:
    """Features F011/F013/F022; FR-011/FR-012/FR-016; PRESERVE."""
    state = MagicMock()
    state.voice_client = MagicMock()
    state.voice_client.is_paused.return_value = False
    state.current_song = _song(0)
    state.loop_mode = LoopMode.NONE
    state.auto_play_enabled = False
    top_songs = [
        {"url": f"https://example.invalid/top/{i}", "title": f"Top {i}", "count": 4 - i}
        for i in range(1, 4)
    ]

    player = MusicPlayerView(MagicMock(), state, top_songs)
    assert len(player.children) == 12
    assert [str(item.emoji) for item in player.children[:5]] == [
        "⏸️",
        "⏭️",
        "⏹️",
        "⭐",
        "📜",
    ]
    assert [item.label for item in player.children[5:9]] == [
        "반복 없음",
        "추천재생: OFF",
        "보관함",
        "노래 검색",
    ]

    state.queue = [_song(i) for i in range(3)]
    queue = QueueManagementView(MagicMock(), state)
    assert [type(item).__name__ for item in queue.children] == [
        "QueueSelect",
        "Button",
        "Button",
        "Button",
        "Button",
    ]
    assert [item.label for item in queue.children[1:]] == [
        "맨 위로",
        "삭제",
        "섞기",
        "전체삭제",
    ]
    assert [item.custom_id for item in queue.children[1:3]] == [
        "q_move_top",
        "q_remove",
    ]


def test_f013_f025_fr012_fr020_preserve_select_modal_and_favorite_contract() -> None:
    """Features F013/F025; FR-012/FR-020; PRESERVE."""
    results = [
        {"title": "결과", "uploader": "채널", "duration": 185},
    ]
    search = SearchSelect(MagicMock(), results)
    assert search.placeholder == "재생할 노래를 선택하세요..."
    assert [(option.label, option.value, option.description) for option in search.options] == [
        ("결과", "0", "채널: 채널 | 길이: 3:05")
    ]

    modal = SearchSongModal(MagicMock())
    assert modal.title == "🎵 노래 검색 및 재생"
    assert modal.timeout == 180
    assert [item._underlying.label for item in modal.children] == [  # type: ignore[attr-defined]
        "검색어 또는 유튜브 URL 입력"
    ]

    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.id = 777
    favorites = [
        {"title": f"Favorite {i}", "url": f"https://example.invalid/f/{i}"}
        for i in range(3)
    ]
    view = FavoritesView(MagicMock(), interaction, favorites)
    assert view.user_id == "777"
    assert [item.label for item in view.children[1:]] == [
        "전체 선택",
        "선택 해제",
        "대기열에 추가",
        "삭제 모드로 전환",
    ]


def test_f009_f010_fr028_fr029_preserve_summary_components() -> None:
    """Features F009/F010; FR-028/FR-029; PRESERVE."""
    cog = MagicMock()
    topics = [{"title": "주제 A"}, {"title": "주제 B"}]
    view = SummaryView(6.0, topics, cog)
    assert view.timeout == 3600
    assert [type(item).__name__ for item in view.children] == [
        "Button",
        "Button",
        "Select",
    ]
    assert [item.label for item in view.children[:2]] == ["새로고침", "고급 요약"]
    assert [option.value for option in view.children[2].options] == ["0", "1"]

    modal = AdvancedSummaryModal(6.0, cog)
    assert modal.timeout == 300
    assert [item._underlying.label for item in modal.children] == [  # type: ignore[attr-defined]
        "포함할 키워드 (쉼표로 구분)",
        "특정 사용자 이름 (쉼표로 구분)",
        "추가 요청사항",
    ]


def test_f002_f003_f037_f042_fr005_fr038_fr043_preserve_watch_admin_components() -> None:
    """Features F002/F003/F037/F042; FR-005/FR-038/FR-043; PRESERVE."""
    join = WatchTogetherJoinView("https://watch.invalid/watch?session=abc")
    assert len(join.children) == 1
    assert join.children[0].label == "🎬 시청방 바로 입장"
    assert join.children[0].url == "https://watch.invalid/watch?session=abc"

    close = WatchSessionControlView("abc")
    assert close.timeout == 21600
    assert close.children[0].label == "🛑 세션 강제 종료"
    assert close.children[0].custom_id == "log_agent:close_watch_session"

    restart = RestartControlView()
    assert restart.timeout is None
    assert restart.children[0].label == "🔄 수동 업데이트 및 재시작"
    assert restart.children[0].custom_id == "log_agent:restart_bot"


def test_f022_fr016_preserve_clear_confirmation_components() -> None:
    """Feature F022; FR-016; PRESERVE."""
    view = ConfirmClearView(MagicMock(), MagicMock(), MagicMock())
    assert view.timeout == 30
    assert [item.label for item in view.children] == ["확인", "취소"]


def test_f010_f013_f022_f025_fr021_correct_components_paginate_without_data_loss() -> None:
    """Features F010/F013/F022/F025; FR-021/FR-029; CORRECT; actual V2 Music UI path."""
    from discordbot.music.adapters.discord_ui import build_song_view
    from discordbot.music.domain.model import Track
    from discordbot.music.domain.pages import SongPages

    songs = tuple(Track(str(i), f"https://example.invalid/{i}", "Duplicate", 200, 10) for i in range(26))
    pages = SongPages(100, 10, 999, songs)
    queue = build_song_view(MagicMock(), pages, "queue")
    try:
        assert len(queue.songs) == 26
        assert any(getattr(item, "label", None) == "다음" for item in queue.children)
        assert pages.page(1)[0].item_id == "25"
        assert pages.select(("25",), 100, 10, 1)[0] == songs[25]
    finally:
        queue.stop()


@pytest.mark.asyncio
async def test_f010_fr029_correct_summary_topics_paginate_with_stable_ids() -> None:
    """Feature F010; FR-029; CORRECT; Summary owner split from remaining PHASE 7 spec."""
    from characterization.summary_support import harness, interaction
    from discordbot.summary.adapters.discord_ui import SummaryController
    from discordbot.summary.domain.models import Query

    fixture = harness(topics=26)
    controller = SummaryController(fixture.service)
    try:
        first = interaction()
        await controller.execute(first, Query())
        result = next(iter(fixture.service._results.values()))
        navigation = interaction()
        view = first.followup.send.call_args.kwargs["view"]
        await next(item for item in view.children if getattr(item, "label", "") == "다음").callback(navigation)
        second_page = navigation.response.edit_message.call_args.kwargs["view"]
        assert [option.value for option in second_page.children[2].options] == [f"{result.id}:25"]
        detail = interaction()
        detail.data["values"] = [f"{result.id}:25"]
        await second_page.children[2].callback(detail)
        assert detail.response.send_message.call_args.kwargs["ephemeral"] is True
        assert "26" in detail.response.send_message.call_args.kwargs["embed"].title
        assert len(result.summary.topics) == 26
    finally:
        controller.close()
        await fixture.service.stop()
