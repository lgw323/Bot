"""Pure, bounded public status projection; no Money DB, credentials or I/O."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import re

MAXIMUM_BYTES = 2048
MAXIMUM_AGE = 180
MAXIMUM_BACKUP_AGE = 6*3600
PROCESS = {'not_installed': '미설치 보고', 'running': '실행 중 보고',
           'stopped': '중지 보고', 'failed': '실패 보고', 'unknown': '미확인'}
HEALTH = {'pass': '통과 보고', 'fail': '미통과 보고', 'unknown': '미확인'}
SCHEMA = {'compatible': '호환 보고', 'incompatible': '비호환 보고', 'unknown': '미확인'}
BACKUP = {'pass': '검증 통과 보고', 'fail': '검증 실패 보고', 'unknown': '미확인'}
SCOPE = '최소 상태 투영만 표시 · 금액·거래·계정·세션·키·DB 및 복원 직접 검사 아님'


class MoneyProjectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MoneyObservation:
    observed_at: datetime
    process: str
    health: str
    schema: str
    artifact_sha256: str | None
    backup: str
    backup_verified_at: datetime | None


def _utc(value: object) -> datetime:
    if type(value) is not str or not 1 <= len(value) <= 40:
        raise ValueError
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
        raise ValueError
    return result.astimezone(timezone.utc)


def is_current(value: MoneyObservation, now: datetime) -> bool:
    if (type(value) is not MoneyObservation or type(now) is not datetime or now.tzinfo is None
            or now.utcoffset() != timezone.utc.utcoffset(now)):
        return False
    age = (now-value.observed_at).total_seconds()
    return 0 <= age <= MAXIMUM_AGE


def current_projection(value: MoneyObservation | None, now: datetime) -> MoneyObservation | None:
    """Re-evaluate both deadlines at display time without reading or retaining data."""
    if not is_current(value,now):
        return None
    if value.backup_verified_at is not None and (now-value.backup_verified_at).total_seconds() > MAXIMUM_BACKUP_AGE:
        return replace(value,backup='unknown',backup_verified_at=None)
    return value


def parse_projection(raw: bytes, now: datetime) -> MoneyObservation:
    """Unknown fields (including financial/auth fields) reject the entire input."""
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAXIMUM_BYTES:
            raise ValueError
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        def constant(_value):
            raise ValueError
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=constant)
        keys = {'version','service','observed_at','process','health','schema','artifact_sha256','backup','backup_verified_at'}
        if (type(value) is not dict or set(value) != keys or type(value['version']) is not int
                or value['version'] != 1 or value['service'] != 'mymoney'
                or any(type(value[key]) is not str or value[key] not in allowed for key,allowed in
                       (('process',PROCESS),('health',HEALTH),('schema',SCHEMA),('backup',BACKUP)))):
            raise ValueError
        artifact = value['artifact_sha256']
        if artifact is not None and (type(artifact) is not str or re.fullmatch('[a-f0-9]{64}',artifact) is None):
            raise ValueError
        observed = _utc(value['observed_at'])
        verified = None if value['backup_verified_at'] is None else _utc(value['backup_verified_at'])
        if (value['backup'] == 'unknown') != (verified is None) or verified is not None and verified > observed:
            raise ValueError
        if value['process'] != 'running' and (value['health'] != 'unknown' or value['schema'] != 'unknown'
                or artifact is not None):
            raise ValueError
        if value['process'] in {'not_installed','unknown'} and value['backup'] != 'unknown':
            raise ValueError
        if value['health'] != 'pass' and value['schema'] != 'unknown':
            raise ValueError
        if value['health'] == 'pass' and value['process'] != 'running':
            raise ValueError
        result = current_projection(MoneyObservation(observed,value['process'],value['health'],value['schema'],artifact,value['backup'],verified),now)
        if result is None:
            raise ValueError
        return result
    except (ValueError,TypeError,UnicodeError,OverflowError,RecursionError):
        raise MoneyProjectionError('invalid_or_noncurrent_money_status_projection') from None
