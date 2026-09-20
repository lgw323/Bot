"""Test-process credential boundary, installed before application collection.

Automatic dotenv loading is disabled; tests supply explicit mappings/monkeypatches.
The process-lifetime audit hook also rejects direct reads of repository dotenv files.
This module is pytest-only and is never imported by the production entrypoints.
"""

import os
import sys
from typing import Any

import dotenv
import dotenv.main


_REPOSITORY = os.path.normcase(os.path.realpath(os.path.dirname(__file__)))


def _deny_repository_credentials(event: str, args: tuple[Any, ...]) -> None:
    if event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    # Do not use Path.resolve here: filesystem tests replace it with a model
    # that reads files, which would recursively trigger this audit hook.
    path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
    # Check the requested name first: .env itself may point outside the repo.
    # Then check the resolved name to catch an alias pointing into the repo.
    for candidate in (path, os.path.normcase(os.path.realpath(path))):
        name = os.path.basename(candidate)
        if os.path.dirname(candidate) == _REPOSITORY and (name == ".env" or name.startswith(".env.")):
            raise PermissionError("pytest forbids repository credential file access")


sys.addaudithook(_deny_repository_credentials)

# Clear application configuration inherited from the launching shell without
# inspecting its values. Missing credentials remain missing, not fake production
# credentials. OS/tool settings (PATH, SYSTEMROOT, etc.) are deliberately retained.
_LEGACY_SETTINGS = {
    "MASTER_USER_ID", "LOG_CHANNEL_ID", "SUMMARY_CHANNEL_ID", "DEFAULT_SUMMARY_HOURS",
    "LOG_RETENTION_HOURS", "INITIAL_LOAD_HOURS", "MAX_LOG_COUNT", "MAX_HISTORY_FETCH",
    "PRUNE_INTERVAL_MINUTES", "GEMINI_MODEL", "TIMEZONE_OFFSET_HOURS",
    "DEFAULT_MAX_REQUEST_TOKENS", "MAX_RESPONSE_TOKENS", "TEMPERATURE", "DEBUG_MODE",
}
for _name in tuple(os.environ):
    if _name in _LEGACY_SETTINGS or _name.startswith(
        ("DISCORD_", "GOOGLE_", "DB_", "MUSIC_", "YTDLP_", "WATCH_", "APP_", "PLATFORM_")
    ):
        os.environ.pop(_name, None)

os.environ["PYTHON_DOTENV_DISABLED"] = "1"  # Also inherited by test child processes.


def _no_automatic_dotenv(*args: Any, **kwargs: Any) -> bool:
    # Short-circuit before path discovery/stat/open, including if a test clears
    # os.environ or the installed python-dotenv predates its opt-out variable.
    return False


dotenv.load_dotenv = _no_automatic_dotenv
dotenv.main.load_dotenv = _no_automatic_dotenv
