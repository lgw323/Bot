"""Credential isolation must precede test collection, not just fixture setup."""

from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", ["main_bot", "cogs.logging.log_agent"])
@pytest.mark.parametrize("protected", [False, True], ids=["unsafe-canary", "protected"])
def test_collection_never_reads_repository_dotenv(
    tmp_path: Path, module: str, protected: bool,
) -> None:
    # Only copy source files. Never copy the developer's configuration or data.
    for source in [ROOT / "main_bot.py", ROOT / "database_manager.py", *ROOT.glob("cogs/**/*.py")]:
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (tmp_path / ".env").write_text("DISCORD_TOKEN=synthetic-canary\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    # Installed before either the guard or application imports. It fails before
    # opening the synthetic canary and never needs access to the real .env.
    probe = '''
from pathlib import Path
import sys
import pytest

CANARY = Path(__file__).parent / ".env"
def detect_canary(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        if Path(args[0]).resolve() == CANARY.resolve():
            CANARY.with_name("access-detected").write_text("detected")
            raise AssertionError("synthetic dotenv access detected")
sys.addaudithook(detect_canary)

@pytest.fixture(autouse=True)
def too_late():
    CANARY.with_name("fixture-ran").write_text("ran")
'''
    bootstrap = ROOT / "conftest.py"
    if protected and bootstrap.exists():
        probe += "\n" + bootstrap.read_text(encoding="utf-8")
    (tmp_path / "conftest.py").write_text(probe, encoding="utf-8")
    (tmp_path / "test_probe.py").write_text(
        f"import {module}\n"
        "import os\n"
        "from pathlib import Path\n"
        "assert 'DISCORD_TOKEN' not in os.environ\n"
        "assert 'GOOGLE_API_KEY' not in os.environ\n"
        "assert 'MASTER_USER_ID' not in os.environ\n"
        "if 'main_bot' in globals():\n"
        "    import pytest\n"
        "    from unittest.mock import patch\n"
        "    with patch.object(main_bot, 'MyBot') as bot, patch.object(main_bot.logger, 'critical'):\n"
        "        with pytest.raises(SystemExit): main_bot.main()\n"
        "        bot.assert_not_called()\n"
        "Path(__file__).with_name('import-reached').write_text('reached')\n"
        "def test_collected(): pass\n", encoding="utf-8",
    )
    environment = dict(os.environ)
    environment.pop("PYTHON_DOTENV_DISABLED", None)
    environment.pop("PYTHONPATH", None)
    environment.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1",
        DISCORD_TOKEN="synthetic-inherited", GOOGLE_API_KEY="synthetic-inherited",
        MASTER_USER_ID="123456",
    )
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert not (tmp_path / "fixture-ran").exists()
    if protected:
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / "import-reached").exists()
        assert not (tmp_path / "access-detected").exists()
    else:
        assert result.returncode == 2
        assert (tmp_path / "access-detected").exists()
        assert "synthetic dotenv access detected" in result.stdout


def test_direct_repository_dotenv_access_fails_closed(tmp_path: Path) -> None:
    # Deliberate bypass attempts target only a synthetic repository, never real secrets.
    shutil.copyfile(ROOT / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / ".env").write_text("DISCORD_TOKEN=synthetic-canary\n", encoding="utf-8")
    script = '''
import os, runpy
from pathlib import Path
from unittest.mock import patch
import dotenv
runpy.run_path('conftest.py')
os.environ.pop('PYTHON_DOTENV_DISABLED', None)
assert dotenv.load_dotenv() is False
assert dotenv.main.load_dotenv('.env') is False
assert 'DISCORD_TOKEN' not in os.environ
with patch.object(Path, 'resolve', side_effect=AssertionError('mockable path resolution')):
    for reader in (lambda: Path('.env').read_text(), lambda: dotenv.dotenv_values('.env')):
        try:
            reader()
        except PermissionError as error:
            assert 'repository credential file' in str(error)
        else:
            raise AssertionError('credential boundary bypassed')
assert dotenv.dotenv_values(stream=__import__('io').StringIO('SYNTHETIC=explicit')) == {'SYNTHETIC': 'explicit'}
'''
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
