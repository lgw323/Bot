"""Pure local panel generations; no Discord calls, production state or deletion."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from discordbot.operations.adapters.filesystem import atomic_json, read_json
from discordbot.operations.adapters.panel_store import PanelStore
from discordbot.platform.errors import ValidationError


NOW = datetime(2026, 10, 31, 8, 10, tzinfo=timezone.utc)


def published(store, message=100):
    row, fresh = store.claim()
    assert fresh
    store.published(row['nonce'], message, NOW)
    return store.read()


def legacy(state, *, status='published', message=100):
    row = {'version': 1, 'channel': 42, 'message': message,
           'nonce': 'a'*24, 'state': status}
    atomic_json(state/'operations-panel.json', row)
    return row


def test_initial_claim_is_durable_and_never_repeated_after_restart(tmp_path):
    first = PanelStore(tmp_path, 42)
    row, fresh = first.claim()
    assert fresh and row['version'] == 2 and row['previous'] is None
    assert row['message'] is None and row['published_at'] is None
    assert datetime.fromisoformat(row['created_at']).utcoffset() == timedelta(0)
    assert PanelStore(tmp_path, 42).claim() == (row, False)
    assert len((tmp_path/'operations-panel.json').read_bytes()) < 1024


def test_replacement_is_claimed_before_acknowledgment_and_previous_is_bounded(tmp_path):
    store = PanelStore(tmp_path, 42)
    old = published(store)
    pending = store.rotate(old)
    assert pending['state'] == 'publishing' and pending['message'] is None
    assert pending['previous'] == old['message'] == 100
    assert pending['nonce'] != old['nonce']
    rebooted = PanelStore(tmp_path, 42)
    assert rebooted.claim() == (pending, False)  # An uncertain send is not sent anew.
    with pytest.raises(ValidationError): rebooted.rotate(pending)
    with pytest.raises(ValidationError): rebooted.replace_missing(pending)
    with pytest.raises(ValidationError): rebooted.retired(100)
    assert rebooted.read() == pending


def test_acknowledged_new_id_is_durable_before_old_panel_retirement(tmp_path):
    store = PanelStore(tmp_path, 42)
    old = published(store)
    pending = store.rotate(old)
    # An externally verified exact author+nonce reconciliation uses this same ACK.
    store.published(pending['nonce'], 200, NOW.astimezone(timezone(timedelta(hours=9))))
    current = store.read()
    assert current['message'] == 200 and current['previous'] == 100
    assert current['published_at'] == NOW.isoformat(timespec='seconds')
    assert PanelStore(tmp_path, 42).read() == current
    with pytest.raises(ValidationError): store.rotate(current)
    with pytest.raises(ValidationError): store.replace_missing(current)
    with pytest.raises(ValidationError): store.retired(999)
    assert store.read() == current
    cleared = store.retired(100)
    assert cleared['message'] == 200 and cleared['previous'] is None
    assert cleared['nonce'] == pending['nonce']
    assert store.rotate(cleared)['previous'] == 200


def test_stale_rotation_ack_and_retirement_cannot_overwrite_new_generation(tmp_path):
    store = PanelStore(tmp_path, 42)
    first = published(store)
    pending = store.rotate(first)
    for nonce, message in [(first['nonce'], 200), (pending['nonce'], 100)]:
        with pytest.raises(ValidationError): store.published(nonce, message)
    assert store.read() == pending
    store.published(pending['nonce'], 200, NOW)
    store.retired(100)
    current = store.read()
    with pytest.raises(ValidationError): store.rotate(first)
    with pytest.raises(ValidationError): store.published(pending['nonce'], 300)
    with pytest.raises(ValidationError): store.retired(100)
    assert store.read() == current


def test_legacy_published_state_is_read_unchanged_and_migrates_only_with_rotation(tmp_path):
    old = legacy(tmp_path)
    original_bytes = (tmp_path/'operations-panel.json').read_bytes()
    store = PanelStore(tmp_path, 42)
    assert store.read() == old and store.claim() == (old, False)
    assert (tmp_path/'operations-panel.json').read_bytes() == original_bytes
    pending = store.rotate(old)
    assert pending['version'] == 2 and pending['previous'] == 100
    assert pending['nonce'] != old['nonce']


def test_legacy_uncertain_publication_can_only_be_acknowledged_not_reclaimed(tmp_path):
    old = legacy(tmp_path, status='publishing', message=None)
    store = PanelStore(tmp_path, 42)
    assert store.claim() == (old, False)
    with pytest.raises(ValidationError): store.rotate(old)
    with pytest.raises(ValidationError): store.replace_missing(old)
    store.published(old['nonce'], 200, NOW)
    current = store.read()
    assert current['version'] == 2 and current['message'] == 200 and current['previous'] is None


@pytest.mark.parametrize('use_legacy', [True, False])
def test_confirmed_missing_current_replacement_does_not_retain_nonexistent_old_panel(tmp_path, use_legacy):
    store = PanelStore(tmp_path, 42)
    old = legacy(tmp_path) if use_legacy else published(store)
    pending = store.replace_missing(old)
    assert pending['message'] is None and pending['previous'] is None
    assert pending['version'] == 2 and pending['nonce'] != old['nonce']
    assert PanelStore(tmp_path, 42).claim() == (pending, False)
    with pytest.raises(ValidationError): store.replace_missing(old)


@pytest.mark.parametrize('key,value', [
    ('version', True), ('version', 3), ('channel', True), ('channel', 99),
    ('message', True), ('message', 0), ('message', 2**63),
    ('nonce', 'invalid'), ('nonce', True), ('state', 'retiring'),
    ('previous', True), ('previous', 0), ('previous', 100),
    ('created_at', '2026-10-31T08:10:00'), ('created_at', 'PRIVATE'),
    ('created_at', '0001-01-01T00:00:00+01:00'),
    ('published_at', None), ('published_at', 'PRIVATE'),
])
def test_invalid_persisted_generation_fails_closed(tmp_path, key, value):
    store = PanelStore(tmp_path, 42)
    row = published(store)
    atomic_json(store.path, {**row, key: value})
    with pytest.raises(ValidationError): store.read()


@pytest.mark.parametrize('value', [True, 0, 2**63, '100', None])
def test_invalid_acknowledged_or_retired_message_never_changes_state(tmp_path, value):
    store = PanelStore(tmp_path, 42)
    row, _ = store.claim()
    with pytest.raises(ValidationError): store.published(row['nonce'], value)
    assert store.read() == row
    with pytest.raises(ValidationError): store.retired(value)
    assert store.read() == row


def test_invalid_timestamp_and_nonce_do_not_change_claim(tmp_path):
    store = PanelStore(tmp_path, 42)
    row, _ = store.claim()
    for nonce, stamp in [(row['nonce'], NOW.replace(tzinfo=None)), ('b'*24, NOW), ('PRIVATE', NOW)]:
        with pytest.raises(ValidationError): store.published(nonce, 200, stamp)
        assert store.read() == row


def test_duplicate_keys_and_unexpected_fields_are_rejected(tmp_path):
    store = PanelStore(tmp_path, 42)
    row = published(store)
    atomic_json(store.path, {**row, 'private': 'PRIVATE'})
    with pytest.raises(ValidationError): store.read()
    store.path.write_text(json.dumps(row)[:-1] + ',"nonce":"'+'b'*24+'"}', encoding='utf-8')
    from discordbot.platform.errors import DataIntegrityError
    with pytest.raises(DataIntegrityError): store.read()


def test_retirement_only_changes_marker_and_never_touches_other_files(tmp_path):
    store = PanelStore(tmp_path, 42)
    sentinel = tmp_path/'logs-to-preserve.txt'
    sentinel.write_text('synthetic log', encoding='utf-8')
    old = published(store)
    pending = store.rotate(old)
    store.published(pending['nonce'], 200, NOW)
    before = store.read()
    after = store.retired(100)
    assert {**before, 'previous': None} == after
    assert sentinel.read_text(encoding='utf-8') == 'synthetic log'
    assert read_json(store.path) == after


def test_two_readers_cannot_claim_two_replacements_of_same_panel(tmp_path):
    first = PanelStore(tmp_path, 42)
    expected = published(first)
    second = PanelStore(tmp_path, 42)
    assert second.read() == expected
    replacement = first.rotate(expected)
    with pytest.raises(ValidationError): second.rotate(expected)
    assert second.read() == replacement
    assert second.claim() == (replacement, False)


@pytest.mark.parametrize('missing', [False, True])
def test_reused_nonce_cannot_create_a_new_generation(tmp_path, monkeypatch, missing):
    from types import SimpleNamespace
    from discordbot.operations.adapters import panel_store as module
    store = PanelStore(tmp_path, 42)
    old = published(store)
    monkeypatch.setattr(module, 'uuid4', lambda: SimpleNamespace(hex=old['nonce']+'0'*8))
    with pytest.raises(ValidationError, match='nonce reused'):
        store.replace_missing(old) if missing else store.rotate(old)
    assert store.read() == old


@pytest.mark.parametrize('stage', ['claim', 'rotate', 'published', 'retired', 'missing'])
def test_failed_atomic_transition_preserves_existing_marker(tmp_path, monkeypatch, stage):
    from discordbot.operations.adapters import panel_store as module
    store = PanelStore(tmp_path, 42)
    if stage == 'claim':
        before = None
        transition = store.claim
    else:
        old = published(store)
        if stage in {'rotate', 'missing'}:
            transition = (lambda: store.rotate(old)) if stage == 'rotate' else (lambda: store.replace_missing(old))
        else:
            pending = store.rotate(old)
            if stage == 'published':
                transition = lambda: store.published(pending['nonce'], 200, NOW)
            else:
                store.published(pending['nonce'], 200, NOW)
                transition = lambda: store.retired(100)
        before = store.read()
    def fail(*args): raise OSError('synthetic fsync failure')
    monkeypatch.setattr(module, 'atomic_json', fail)
    with pytest.raises(OSError): transition()
    assert store.read() == before


@pytest.mark.parametrize('stage', ['rotate', 'published', 'retired'])
def test_write_committed_then_observer_failed_never_reclaims_unknown_send(tmp_path, monkeypatch, stage):
    from discordbot.operations.adapters import panel_store as module
    store = PanelStore(tmp_path, 42)
    old = published(store)
    if stage == 'rotate':
        transition = lambda: store.rotate(old)
    else:
        pending = store.rotate(old)
        if stage == 'published':
            transition = lambda: store.published(pending['nonce'], 200, NOW)
        else:
            store.published(pending['nonce'], 200, NOW)
            transition = lambda: store.retired(100)
    write = module.atomic_json
    def fail_after_commit(*args):
        write(*args)
        raise OSError('synthetic observer failure after atomic replace')
    monkeypatch.setattr(module, 'atomic_json', fail_after_commit)
    with pytest.raises(OSError): transition()
    current = store.read()
    rebooted = PanelStore(tmp_path, 42)
    assert rebooted.claim() == (current, False)
    if stage == 'rotate':
        assert current['state'] == 'publishing' and current['previous'] == 100
    elif stage == 'published':
        assert current['message'] == 200 and current['previous'] == 100
    else:
        assert current['message'] == 200 and current['previous'] is None
