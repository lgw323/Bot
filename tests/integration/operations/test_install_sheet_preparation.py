import pytest

from .test_production_tools import tool


def test_preparation_adds_only_reviewed_remote_without_mutating_input():
    module = tool('production/prepare_install_sheet.py')
    value = {'environment': 'production', 'backup_remote': None, 'paths': {'database': '/private/candidate'}}
    prepared = module.prepare(value, module.CONFIG_SHA, module.DB_SHA)
    assert prepared == dict(value, backup_remote=module.REMOTE)
    assert value['backup_remote'] is None


@pytest.mark.parametrize('change', ['config_sha', 'db_sha', 'environment', 'remote'])
def test_preparation_rejects_changed_identity_or_configuration(change):
    module = tool('production/prepare_install_sheet.py')
    value = {'environment': 'production', 'backup_remote': None}
    config_sha, db_sha = module.CONFIG_SHA, module.DB_SHA
    if change == 'config_sha':
        config_sha = 'changed'
    elif change == 'db_sha':
        db_sha = 'changed'
    elif change == 'environment':
        value['environment'] = 'staging'
    else:
        value['backup_remote'] = {'repository': 'unreviewed'}
    with pytest.raises(ValueError):
        module.prepare(value, config_sha, db_sha)
