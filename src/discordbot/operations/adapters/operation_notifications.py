"""Last-operation notifications, with an explicit uncertain-delivery boundary.

Only the validated last outcome and one private cursor survive restart. General
error notices stay in the bounded RAM queue. The cursor is claimed before send:
an interrupted/uncertain send is not replayed blindly after process restart.
The panel can still show the durable outcome even when its alert was lost.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from discordbot.operations.adapters.filesystem import atomic_json, identifier
from discordbot.operations.adapters.operation_results import _read, read_operation_result, validate_operation_result, TERMINAL
from discordbot.platform.errors import DataIntegrityError


def operation_key(row: dict[str, Any]) -> str:
    return row['id'] + ':' + row['result']


def _cursor(path: Path) -> dict[str, Any] | None:
    value = _read(path)
    try:
        if value is not None and (set(value) != {'version', 'key', 'phase'} or type(value['version']) is not int
                or value['version'] != 1 or not isinstance(value['key'], str)
                or not re.fullmatch(r'[a-f0-9]{32}:(?:ok|failed|ok_cleanup_failed)', value['key'])
                or value['phase'] not in {'claimed', 'delivered', 'rejected'}):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise DataIntegrityError('operation delivery cursor invalid')
    return value


def _snapshot(state: Path):
    return read_operation_result(state), _cursor(state / 'operation-notice.json')


def _write_cursor(path: Path, key: str, phase: str) -> None:
    value = dict(version=1, key=key, phase=phase)
    if not re.fullmatch(r'[a-f0-9]{32}:(?:ok|failed|ok_cleanup_failed)', key) or phase not in {'claimed', 'delivered', 'rejected'}:
        raise DataIntegrityError('operation delivery cursor invalid')
    atomic_json(path, value)  # Runtime-private 0600; no raw rendered notice storage.


def _age(row: dict[str, Any], now: datetime) -> float:
    return (now.astimezone(timezone.utc) - datetime.fromisoformat(row['timestamp'])).total_seconds()


def startup_description(release: str, row: dict[str, Any] | None, now: datetime) -> str:
    try:
        release = identifier(release)
    except (DataIntegrityError, TypeError):
        release = 'unknown'
    if row is not None:
        try:
            row = validate_operation_result(row)
        except DataIntegrityError:
            row = None
    lines = ['Discord 연결이 확인되었습니다. 전체 서비스의 준비 완료를 뜻하지는 않습니다.',
             '시작 원인: 확인되지 않음', f'배포 버전: {release}',
             f'시각(UTC): {now.astimezone(timezone.utc).isoformat(timespec="seconds")}']
    if row is not None and row['result'] == 'in_progress' and -60 <= _age(row, now) <= 600:
        action = '업데이트' if row['operation'] == 'update' else '재시작'
        source = {'manual': '관리자 요청', 'operator': '운영 CLI', 'scheduled': '예약 정책',
                  'unknown': '실행 경로 미확인'}[row['source']]
        lines.append(f'확인된 최근 운영 기록: {source} {action} 진행 중. 최종 완료 검증 대기.')
        lines.append('이 기록만으로 이번 연결의 직접 원인을 확정하지 않습니다.')
    return '\n'.join(lines)


def result_message(row: dict[str, Any]) -> tuple[str, str, int]:
    row = validate_operation_result(row)  # Revalidate the export boundary too.
    action = '업데이트' if row['operation'] == 'update' else '재시작'
    result = row['result']
    titles = {'ok': f'✅ {action} 완료 검증', 'ok_cleanup_failed': f'⚠️ {action} 완료 · 정리 확인 필요',
              'failed': f'❌ {action} 실패'}
    detail = {'ok': '운영 작업의 실제 완료 검증 기록을 확인했습니다.',
              'ok_cleanup_failed': '서비스는 완료 검증을 통과했지만 이전 파일 정리가 실패했습니다.',
              'failed': '운영 작업이 실패했습니다. 정상 서비스 복구 여부는 상태 화면에서 확인하세요.'}
    if result not in TERMINAL:
        raise DataIntegrityError('nonterminal operation cannot announce completion')
    unchanged = row['operation'] == 'update' and result == 'ok' and row['stage'] == 'unchanged'
    if unchanged:
        titles['ok'] = 'ℹ️ 업데이트 확인 · 변경 없음'
        detail['ok'] = '현재 배포본과 후보가 같아 업데이트·재시작을 실행하지 않았습니다. 서비스 건강 상태를 검증했다는 뜻은 아닙니다.'
    text = '\n'.join([detail[result], f"작업: {action}", f"단계: {row['stage']}",
        f"배포 버전: {row['release']}", f"시각(UTC): {row['timestamp']}", f"작업 추적: {row['id']}"])
    return titles[result], text, 0x3498DB if unchanged else 0x2ECC71 if result == 'ok' else 0xF1C40F if result == 'ok_cleanup_failed' else 0xFF0000


class OperationNotifications:
    """One bounded executor operation per poll/transition; no background task."""
    def __init__(self, state: Path, executor: Any) -> None:
        self.state, self.executor = state, executor
        self.queued: str | None = None
        self.current: dict[str, Any] | None = None
        self.uncertain = 0
        self.last_uncertain: str | None = None

    async def snapshot(self, now: datetime) -> dict[str, Any] | None:
        row, cursor = await self.executor.run(_snapshot, self.state)
        self.current = row
        if row is None or row['result'] not in TERMINAL or not -60 <= _age(row, now) <= 86400:
            return None
        key = operation_key(row)
        if cursor is not None and cursor['key'] == key:
            if cursor['phase'] == 'claimed' and self.last_uncertain != key:
                self.uncertain += 1
                self.last_uncertain = key
            return None
        if self.queued == key:
            return None
        return row

    def admitted(self, row: dict[str, Any]) -> None:
        self.queued = operation_key(row)

    async def claim(self, key: str) -> None:
        # Retain just this bounded atomic local write on cancellation. Never
        # start a network request unless the uncertain boundary is persisted.
        owner = asyncio.current_task()
        cancelling = owner.cancelling()
        await self.executor.run_retained(_write_cursor, self.state / 'operation-notice.json', key, 'claimed')
        if owner.cancelling() > cancelling:
            raise asyncio.CancelledError

    async def delivered(self, key: str) -> None:
        await self._transition(key, 'delivered')

    async def rejected(self, key: str) -> None:
        await self._transition(key, 'rejected')

    async def _transition(self, key: str, phase: str) -> None:
        owner = asyncio.current_task()
        cancelling = owner.cancelling()
        await self.executor.run_retained(_write_cursor, self.state / 'operation-notice.json', key, phase)
        if owner.cancelling() > cancelling:
            raise asyncio.CancelledError
