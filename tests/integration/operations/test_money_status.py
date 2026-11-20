"""Legacy status projection parser; no financial DB, keys, HTTP or Discord."""
from datetime import timedelta, timezone
import json
from unittest.mock import patch

import pytest

from discordbot.operations.adapters.money_status import MAXIMUM_BYTES, MoneyProjectionError, parse_projection
from .test_unified_panel import NOW


def value(**changes):
    return dict(version=1,service='mymoney',observed_at=NOW.isoformat(),process='running',health='pass',
        schema='compatible',artifact_sha256='a'*64,backup='pass',
        backup_verified_at=(NOW-timedelta(hours=1)).isoformat()) | changes


def payload(**changes):
    return json.dumps(value(**changes),separators=(',',':')).encode()


def test_minimal_projection_is_bounded_and_only_public_metadata_survives():
    parsed=parse_projection(payload(),NOW)
    assert parsed.process=='running' and parsed.artifact_sha256=='a'*64
    assert parsed.backup_verified_at==NOW-timedelta(hours=1)
    assert len(payload())<MAXIMUM_BYTES


@pytest.mark.parametrize('field',['balance','amount','transactions','accounts','session','api_key','db_path','tables'])
def test_financial_auth_or_other_unknown_fields_reject_without_echo(field):
    with pytest.raises(MoneyProjectionError,match='^invalid_or_noncurrent_money_status_projection$') as error:
        parse_projection(payload(**{field:'PRIVATE synthetic'}),NOW)
    assert 'PRIVATE' not in str(error.value)


@pytest.mark.parametrize('raw',[b'',b'[]',b'\xff',b' '*2049,
    payload().replace(b'"version":1',b'"version":1,"version":1'),
    payload().replace(b'"version":1',b'"version":NaN'),
    payload().replace(b'"health":"pass"',b'"health":{}')])
def test_bad_type_duplicate_nan_invalid_utf8_and_size_are_rejected(raw):
    with pytest.raises(MoneyProjectionError):parse_projection(raw,NOW)


@pytest.mark.parametrize('change',[{'version':True},{'service':'other'},{'process':'PRIVATE'},
    {'artifact_sha256':'a'*40},{'artifact_sha256':'../PRIVATE'},
    {'observed_at':NOW.replace(tzinfo=None).isoformat()},
    {'observed_at':NOW.astimezone(timezone(timedelta(hours=9))).isoformat()},
    {'observed_at':(NOW+timedelta(seconds=1)).isoformat()},
    {'observed_at':(NOW-timedelta(seconds=181)).isoformat()}])
def test_schema_identity_timestamp_and_noncurrent_proofs_fail_closed(change):
    with pytest.raises(MoneyProjectionError):parse_projection(payload(**change),NOW)


def test_exact_freshness_boundary_and_uninstalled_cross_validation():
    assert parse_projection(payload(observed_at=(NOW-timedelta(seconds=180)).isoformat(),
        backup='unknown',backup_verified_at=None),NOW)
    absent=dict(process='not_installed',health='unknown',schema='unknown',artifact_sha256=None,
                backup='unknown',backup_verified_at=None)
    assert parse_projection(payload(**absent),NOW).process=='not_installed'
    for change in ({'health':'pass'},{'schema':'compatible'},{'artifact_sha256':'a'*64},
                   {'backup':'pass','backup_verified_at':NOW.isoformat()}):
        with pytest.raises(MoneyProjectionError):parse_projection(payload(**(absent|change)),NOW)


@pytest.mark.parametrize('change',[
    {'process':'stopped','health':'unknown','schema':'compatible','artifact_sha256':None},
    {'process':'stopped','health':'unknown','schema':'unknown','artifact_sha256':'a'*64},
    {'process':'failed','health':'fail','schema':'unknown','artifact_sha256':None},
    {'process':'unknown','health':'unknown','schema':'unknown','artifact_sha256':None},
    {'health':'fail','schema':'compatible'}, {'health':'unknown','schema':'compatible'},
])
def test_contradictory_projection_is_rejected_like_the_producer_contract(change):
    with pytest.raises(MoneyProjectionError):parse_projection(payload(**change),NOW)


@pytest.mark.parametrize('change',[{'backup_verified_at':None},{'backup':'unknown'},
    {'backup_verified_at':(NOW+timedelta(seconds=1)).isoformat()},
    {'backup_verified_at':'PRIVATE'}])
def test_backup_claim_needs_its_own_valid_prior_verification_time(change):
    with pytest.raises(MoneyProjectionError):parse_projection(payload(**change),NOW)


def test_backup_older_than_six_hours_is_unknown_without_erasing_other_observations():
    value=parse_projection(payload(backup_verified_at=(NOW-timedelta(hours=6,seconds=1)).isoformat()),NOW)
    assert value.process=='running' and value.health=='pass'
    assert value.backup=='unknown' and value.backup_verified_at is None
    delayed=parse_projection(payload(observed_at=(NOW-timedelta(seconds=120)).isoformat(),
        backup_verified_at=(NOW-timedelta(hours=6,seconds=1)).isoformat()),NOW)
    assert delayed.backup=='unknown'


def test_parser_never_opens_files_reads_clock_or_calls_network():
    with patch('builtins.open',side_effect=AssertionError('no file read')), \
         patch('time.time',side_effect=AssertionError('no clock read')), \
         patch('socket.create_connection',side_effect=AssertionError('no network')):
        assert parse_projection(payload(),NOW)
