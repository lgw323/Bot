"""C13: every extra release file must prevent activation, regardless of basename."""
import pytest

from discordbot.platform.errors import DataIntegrityError
from tests.integration.operations.test_filesystem import release, symlinks_on_windows


@pytest.mark.parametrize("extra_name", ["settings.json", "manifest.json"], ids=["ordinary-extra-control", "nested-manifest-extra"])
def test_unmanifested_nested_file_never_activates(tmp_path, extra_name):
    store = release(tmp_path, "old")
    release(tmp_path, "new")
    store.activate("old")
    assert store.validate("new")["release"] == "new"
    extra = store.path("new") / "app" / extra_name
    relative = extra.relative_to(store.path("new")).as_posix()
    assert relative not in store.validate("new")["files"]
    extra.write_text('{"synthetic_unreviewed_setting":true}', encoding="utf-8")
    try:
        store.activate("new")
    except DataIntegrityError:
        rejected = True
    else:
        rejected = False
    observed = store.current()
    assert rejected and observed == "old", (
        f"C13 requires extra-file rejection before activation: {relative}; "
        f"rejected={rejected}, current={observed}"
    )
