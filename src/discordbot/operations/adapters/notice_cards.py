"""Presentation of already-redacted notices; no raw logging payloads enter here."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re

from discordbot.operations.adapters.filesystem import identifier
from discordbot.platform.errors import DataIntegrityError
from discordbot.operations.adapters.panel_links import panel_link as validated_panel_link


def safe_release(value: object) -> str:
    try:
        return identifier(value) if type(value) is str else 'unknown'
    except DataIntegrityError:
        return 'unknown'


def display_release(value: object) -> str:
    """Abbreviate public artifact identity only; persisted/full identity is unchanged."""
    release = safe_release(value)
    if release == 'unknown':
        return '미확인'
    match = re.fullmatch(r'r-([a-f0-9]{16})-([a-f0-9]{16})', release)
    if match is not None:
        return f'{match[1][:8]}… / {match[2][:8]}…'
    if re.fullmatch(r'[a-f0-9]{40}', release):
        return release[:8] + '…'
    return release if len(release) <= 24 else release[:20] + '…'


def display_trace(value: object) -> str:
    return value[:8] + '…' if type(value) is str and re.fullmatch(r'[a-f0-9]{32}', value) else '미확인'


def stage_label(value: object) -> str:
    labels = {'accepted': '접수', 'build': '빌드', 'preflight': '사전 검사', 'test': '검사',
        'compatibility': '호환성 검사', 'backup': '백업', 'publish': '배포 준비', 'stop': '서비스 중지',
        'activate': '버전 전환', 'start': '시작', 'readiness': '준비 확인', 'smoke': '기능 확인',
        'audit': '결과 기록', 'retention': '보존본 정리', 'complete': '완료 확인',
        'unchanged': '변경 없음', 'checkpoint': '상태 보존', 'interrupted': '중단 확인', 'unknown': '미확인'}
    return labels.get(value, '미확인') if type(value) is str else '미확인'


def utc_text(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('notice timestamp must be aware')
    return value.astimezone(timezone.utc).isoformat(timespec='seconds')


@dataclass(frozen=True, slots=True)
class CardMetadata:
    # Fields come only from validated builders, never arbitrary record extras.
    fields: tuple[tuple[str, str], ...] = ()
    release: str | None = None
    occurred_at: datetime | None = None
    operation_version: bool = False

    def with_context(self, release: str, now: datetime) -> CardMetadata:
        return replace(self, release=safe_release(release if self.release is None else self.release),
                       occurred_at=now if self.occurred_at is None else self.occurred_at)


def _size(value: str, maximum: int) -> int:
    if type(value) is not str or not value:
        raise ValueError('notice text invalid')
    size = len(value.encode('utf-16-le')) // 2
    if size > maximum:
        raise ValueError('notice text exceeds limit')
    return size


def notice_embed(title: str, description: str, color: int, metadata: CardMetadata, *, panel_link: str | None = None):
    """Fail closed on malformed presentation; never fall back to plain raw text.

    The diagnostic builder clips whole lines before its closing fence. Keep its
    conservative 2,000 UTF-16-unit budget, even inside the larger embed slot.
    """
    import discord
    total = _size(title, 256) + _size(description, 2000)
    if (type(metadata) is not CardMetadata or type(metadata.fields) is not tuple
            or len(metadata.fields) > 25 or type(metadata.operation_version) is not bool):
        raise ValueError('notice metadata invalid')
    label = '작업 기록 버전' if metadata.operation_version else '실행 버전'
    footer = f'{label}: {display_release(metadata.release)} · 시각(UTC): {utc_text(metadata.occurred_at)}'
    total += _size(footer, 2048)
    for item in metadata.fields:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError('notice field invalid')
        total += _size(item[0], 256) + _size(item[1], 1024)
    if total > 6000:
        raise ValueError('notice embed exceeds total limit')
    embed = discord.Embed(title=title, description=description, color=color)
    for name, value in metadata.fields:
        embed.add_field(name=name, value=value, inline=False)
    navigation = validated_panel_link(panel_link)
    if navigation is not None:
        name, value = '운영 제어판', f'[제어판으로 이동]({navigation})'
        # Optional navigation must never displace evidence or drop a notice.
        if len(metadata.fields) < 25 and total + _size(name, 256) + _size(value, 1024) <= 6000:
            embed.add_field(name=name, value=value, inline=False)
    embed.set_footer(text=footer)
    return embed
