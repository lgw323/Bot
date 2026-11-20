"""Fixed, unprivileged service observations. Never an operation executor.

Only allowlisted systemd properties and loopback health contracts are sampled.
No database, environment, credential, journal or deployment receipt is opened.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import json
import os
import re
import subprocess
from typing import Any, Callable

import aiohttp


@dataclass(frozen=True, slots=True)
class ServiceObservation:
    key: str
    label: str
    state: str
    health: str
    health_scope: str
    observed_at: datetime | None
    version: str | None
    version_provenance: str
    recent_job: str
    next_run: datetime | None = None
    enabled: bool | None = None
    last_trigger: datetime | None = None


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    key: str
    label: str
    unit: str
    health_scope: str


SERVICES = (
    ServiceSpec('bot', 'Bot', 'discord-bot.service',
                '런타임 기본 준비 검사. 외부 API·음성 재생 전체 검사는 아님'),
    ServiceSpec('watch', 'Watch', 'watch-web.service',
                'Watch 런타임 기본 준비 검사. 실제 브라우저·WebSocket 이용 검사는 아님'),
    ServiceSpec('salary', 'Salary Meter', 'salary-meter.service', 'systemd 프로세스 상태'),
    ServiceSpec('astral', 'Astral', 'astral-legacy.service', 'systemd 프로세스 상태'),
    ServiceSpec('study', 'Study', 'study-static.service', 'systemd 프로세스 상태'),
    ServiceSpec('cloudflared', 'Cloudflared', 'cloudflared.service',
                'systemd 프로세스 상태 · 공개 경로는 별도 확인'),
    ServiceSpec('backup', '정기 Bot DB 백업', 'discordbot-backup.service',
                '예약 타이머·작업 종료 기록. 업로드·복원 무결성 증명은 별도'),
    ServiceSpec('update', '승인 릴리스 업데이트', 'discordbot-update.service', '예약 타이머·업데이트 작업 종료 기록'),
    ServiceSpec('manual', '수동 요청 처리', 'discordbot-manual.service', '60초 주기 요청함 확인·작업 종료 기록'),
)
PRIMARY_SERVICE_KEYS = tuple(spec.key for spec in SERVICES)
PRIMARY_CHOICES = tuple((spec.key, spec.label) for spec in SERVICES)
LEGACY_PRIMARY_SERVICE_KEYS = ('bot', 'supper', 'forme')
LEGACY_MENUS = (LEGACY_PRIMARY_SERVICE_KEYS, (*LEGACY_PRIMARY_SERVICE_KEYS, 'mymoney'),
                ('bot', 'watch', 'supper', 'forme', 'cloudflared', 'backup'))
TIMERS = {key: f'discordbot-{key}.timer' for key in ('backup', 'update', 'manual')}
TIMER = TIMERS['backup']
UNITS = tuple(s.unit for s in SERVICES) + tuple(TIMERS.values())
PROPERTIES = ('Id', 'LoadState', 'ActiveState', 'SubState', 'Result', 'ExecMainStatus',
              'ExecMainExitTimestamp', 'NextElapseUSecRealtime', 'LastTriggerUSec', 'UnitFileState')
RELEASE = re.compile(r'r-[a-f0-9]{16}-[a-f0-9]{16}\Z')
UNKNOWN_VERSION = '실행 버전 미제공'
NO_JOB = '최근 작업 미확인 · 검증된 기록 미제공'


def unknown_observations() -> tuple[ServiceObservation, ...]:
    return tuple(ServiceObservation(s.key, s.label, '미확인', '미확인', s.health_scope,
                                   None, None, '예약 작업 · 별도 실행 버전 없음' if s.key in TIMERS
                                   else UNKNOWN_VERSION, NO_JOB) for s in SERVICES)


def validate_observations(value: object) -> tuple[ServiceObservation, ...]:
    """One public boundary for both real and injected providers; no raw text."""
    if type(value) is not tuple or len(value) != len(SERVICES):
        raise ValueError('invalid service observations')
    for row, spec in zip(value, SERVICES):
        if (type(row) is not ServiceObservation or any(type(getattr(row, name)) is not str for name in
                ('key', 'label', 'state', 'health', 'health_scope', 'version_provenance', 'recent_job'))
                or row.key != spec.key or row.label != spec.label
                or row.health_scope != spec.health_scope
                or row.state not in {'실행 중', '실행 중 아님', '실패', '예약 대기', '미확인'}
                or row.health not in {'통과', '미통과', '미확인'}
                or row.version is not None and (type(row.version) is not str or RELEASE.fullmatch(row.version) is None)):
            raise ValueError('invalid service observations')
        for stamp in (row.observed_at, row.next_run, row.last_trigger):
            if stamp is not None and (type(stamp) is not datetime or stamp.tzinfo is None
                                      or stamp.utcoffset() != timezone.utc.utcoffset(stamp)):
                raise ValueError('invalid service observation timestamp')
        expected = ('실행 health 응답' if row.version is not None else UNKNOWN_VERSION)
        if row.key in TIMERS:
            expected = '예약 작업 · 별도 실행 버전 없음'
        if row.version_provenance != expected or row.version is not None and row.key not in ('bot', 'watch'):
            raise ValueError('invalid service version evidence')
        if row.recent_job != NO_JOB:
            if row.key == 'manual' and row.recent_job == '처리할 요청 없음':
                pass
            elif row.key not in TIMERS or type(row.recent_job) is not str or re.fullmatch(
                    r'최근 작업 (정상|실패) 종료 · \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00', row.recent_job) is None:
                raise ValueError('invalid service job evidence')
            else:
                datetime.fromisoformat(row.recent_job.split(' · ')[1])
        if (row.enabled is not None and type(row.enabled) is not bool
                or row.key not in TIMERS and (row.next_run is not None or row.last_trigger is not None or row.enabled is not None)):
            raise ValueError('invalid service schedule')
        if row.observed_at is None and (row.state != '미확인' or row.health != '미확인'
                or row.version is not None or row.recent_job != NO_JOB or row.next_run is not None
                or row.enabled is not None or row.last_trigger is not None):
            raise ValueError('service evidence has no observation time')
    return value


def _systemd_time(value: object) -> datetime | None:
    if type(value) is not str or len(value) > 64:
        return None
    for fmt in ('%a %Y-%m-%d %H:%M:%S.%f UTC', '%a %Y-%m-%d %H:%M:%S UTC'):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _unit_rows(output: str) -> dict[str, dict[str, str]]:
    """Reject ambiguous/oversized output, never display unrecognized raw values."""
    if type(output) is not str or len(output) > 16384:
        return {}
    rows: dict[str, dict[str, str]] = {}
    for block in output.strip().split('\n\n'):
        row: dict[str, str] = {}
        for line in block.splitlines():
            key, sep, value = line.partition('=')
            if not sep or key not in PROPERTIES or key in row or len(value) > 256:
                return {}
            row[key] = value
        name = row.get('Id')
        if name not in UNITS or name in rows:
            return {}
        rows[name] = row
    return rows


def _query_units() -> dict[str, dict[str, str]]:
    result = subprocess.run(['/usr/bin/systemctl', 'show', *UNITS,
                             '--property=' + ','.join(PROPERTIES), '--no-pager'],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            encoding='utf-8', errors='strict', timeout=2,
                            env={'PATH': os.defpath, 'LC_ALL': 'C', 'TZ': 'UTC'})
    rows = _unit_rows(result.stdout)
    if not rows:
        return rows
    # list-timers converts monotonic deadlines to wall time, including the manual inbox timer.
    try:
        schedule = subprocess.run(['/usr/bin/systemctl', 'list-timers', '--all', '--no-pager',
                                   '--output=json', *TIMERS.values()], stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=1,
                                  env={'PATH': os.defpath, 'LC_ALL': 'C', 'TZ': 'UTC'})
        if schedule.returncode == 0 and len(schedule.stdout) <= 8192:
            for item in json.loads(schedule.stdout):
                if not isinstance(item, dict):
                    continue
                name, timestamp = item.get('unit'), item.get('next')
                if (name in TIMERS.values() and name in rows and type(timestamp) is int
                        and 0 < timestamp < 253402300799000000):
                    rows[name]['next_epoch_us'] = str(timestamp)
    except (ValueError, TypeError, OSError, subprocess.SubprocessError):
        pass  # Other unit observations and calendar deadlines remain available.
    return rows


async def _health(port: int, path: str) -> tuple[int, dict[str, Any]]:
    # No proxy discovery or redirects. Endpoints,
    # host, port and path are fixed at construction, never supplied by Discord.
    # The total deadline includes headers and trickling bodies; a per-socket
    # inactivity timeout or cancelling an executor awaiter would not bound it.
    async with asyncio.timeout(0.6), aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=0.6), trust_env=False) as session:
        async with session.get(f'http://127.0.0.1:{port}{path}', allow_redirects=False,
                headers={'User-Agent': 'DiscordBot-LocalStatus/1', 'Accept': 'application/json'}) as response:
            if response.status not in (200, 503):
                return response.status, {}
            body = bytearray()
            async for chunk in response.content.iter_chunked(2049):
                body.extend(chunk)
                if len(body) > 2048:
                    return response.status, {}
            status = response.status
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate health property')
                result[key] = value
            return result
        value = json.loads(body, object_pairs_hook=unique)
        return status, value if type(value) is dict else {}


class ReadOnlyServiceStatus:
    """A fresh bounded sample per refresh; no cache of an old healthy result."""

    def __init__(self, executor: Any, *, bot_port: int = 9010, watch_port: int = 9011,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        if any(type(p) is not int or not 1 <= p <= 65535 for p in (bot_port, watch_port)):
            raise ValueError('invalid loopback health port')
        self.executor, self.now = executor, now
        self.endpoints = {'bot': (bot_port, '/health/ready'),
                          'watch': (watch_port, '/health/ready')}

    async def snapshot(self) -> tuple[ServiceObservation, ...]:
        return await self._sample()

    async def _sample(self) -> tuple[ServiceObservation, ...]:
        # Stamp the START, not the end, of sampling so slow/old evidence cannot
        # look newer than it is. Permission/transport errors stay independent.
        observed = self.now()
        if type(observed) is not datetime or observed.tzinfo is None or observed.utcoffset() is None:
            return unknown_observations()
        observed = observed.astimezone(timezone.utc)
        try:
            rows = await self.executor.run(_query_units)
        except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
            rows = {}
        result = []
        for spec in SERVICES:
            row = rows.get(spec.unit, {})
            known = row.get('LoadState') == 'loaded'
            active, sub = row.get('ActiveState'), row.get('SubState')
            state = ('실패' if active == 'failed' else '실행 중' if active == 'active' and sub == 'running'
                     else '실행 중 아님' if active in ('inactive', 'activating', 'deactivating', 'active')
                     else '미확인') if known else '미확인'
            health, version, provenance, job, next_run = '미확인', None, UNKNOWN_VERSION, NO_JOB, None
            sampled = known
            if spec.key in self.endpoints:
                try:
                    status, value = await _health(*self.endpoints[spec.key])
                    sampled = True
                    expected = 'discord-bot' if spec.key == 'bot' else 'watch-web'
                    release = value.get('release')
                    valid = (type(value.get('ready')) is bool and value.get('service') == expected
                             and type(release) is str and RELEASE.fullmatch(release) is not None)
                    if valid:
                        version, provenance = release, '실행 health 응답'
                        health = '통과' if status == 200 and value['ready'] else '미통과'
                    elif status == 503:
                        health = '미통과'
                except (OSError, ValueError, aiohttp.ClientError):
                    pass
            enabled = last_trigger = None
            if spec.key in TIMERS:
                timer = rows.get(TIMERS[spec.key], {})
                sampled = sampled or timer.get('LoadState') == 'loaded'
                timer_loaded = timer.get('LoadState') == 'loaded'
                armed = timer_loaded and timer.get('ActiveState') == 'active'
                if timer_loaded:
                    timer_state = timer.get('ActiveState')
                    if timer_state == 'failed' or active == 'failed':
                        state = '실패'
                    elif armed:
                        state = '실행 중' if active == 'active' else '예약 대기'
                    elif timer_state == 'inactive':
                        state = '실행 중 아님'
                    unit_file = timer.get('UnitFileState')
                    enabled = True if unit_file == 'enabled' else False if unit_file == 'disabled' else None
                    last_trigger = _systemd_time(timer.get('LastTriggerUSec'))
                    if last_trigger is not None and last_trigger > observed:
                        last_trigger = None
                else:
                    state = '미확인'
                stamp = _systemd_time(row.get('ExecMainExitTimestamp'))
                if known and stamp is not None and stamp <= observed:
                    if row.get('Result') == 'success' and row.get('ExecMainStatus') == '0':
                        job = '최근 작업 정상 종료 · ' + stamp.isoformat(timespec='seconds')
                    elif row.get('Result') in ('exit-code', 'timeout', 'signal', 'core-dump', 'oom-kill'):
                        job = '최근 작업 실패 종료 · ' + stamp.isoformat(timespec='seconds')
                if spec.key == 'manual' and known and row.get('Result') == 'exec-condition':
                    job = '처리할 요청 없음'
                if armed:
                    if timer.get('next_epoch_us', '').isdigit():
                        next_run = datetime.fromtimestamp(int(timer['next_epoch_us']) / 1_000_000, timezone.utc)
                    else:
                        next_run = _systemd_time(timer.get('NextElapseUSecRealtime'))
                if next_run is not None and next_run < observed:
                    next_run = None
                provenance = '예약 작업 · 별도 실행 버전 없음'
            result.append(ServiceObservation(spec.key, spec.label, state, health, spec.health_scope,
                                             observed if sampled else None, version, provenance, job, next_run, enabled, last_trigger))
        return tuple(result)
