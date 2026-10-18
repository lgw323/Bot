import pytest

from .test_production_tools import tool


@pytest.mark.parametrize("change", ["marker", "production", "current", "digest", "config"])
def test_corrected_release_guard_refuses_unreviewed_or_production_state(change):
    review = tool("staging/verify_corrected_release.py")
    config = {"environment": "staging", "backup_remote": None, "paths": {"database": "/var/lib/discordbot/data/bot_database.db"}}
    values = [config, review.CONFIG_HASH, True, "inactive", review.PREVIOUS]
    review.guard(*values)
    if change == "config":
        config["environment"] = "production"
    else:
        index = {"digest": 1, "marker": 2, "production": 3, "current": 4}[change]
        values[index] = False if change == "marker" else "unexpected"
    with pytest.raises(ValueError):
        review.guard(*values)
