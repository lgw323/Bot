from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "install_pot_provider.sh"
)


def read_install_script() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_provider_install_is_version_pinned_and_atomic() -> None:
    script = read_install_script()

    assert 'PROVIDER_VERSION="1.3.1"' in script
    assert "git clone --quiet --depth 1 --branch \"$PROVIDER_VERSION\"" in script
    assert "install --allow-scripts=npm:canvas --frozen" in script
    assert 'mv "$candidate_provider" "$PROVIDER_DIR"' in script
    assert 'restore_previous_provider' in script


def test_provider_install_verifies_deno_script_with_cache_permissions() -> None:
    script = read_install_script()

    assert "src/generate_once.ts" in script
    assert "--allow-write=" in script
    assert "--allow-read=" in script
    assert 'chmod 700 "$CACHE_DIR"' in script
    assert 'test "$installed_version" = "$PROVIDER_VERSION"' in script


def test_provider_install_does_not_leave_archived_versions() -> None:
    script = read_install_script()

    assert 'rm -rf -- "$previous_provider"' in script
    assert "archive" not in script.lower()
