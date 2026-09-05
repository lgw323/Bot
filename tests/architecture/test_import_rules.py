from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src" / "discordbot"
FEATURE_CONTEXTS = {"music", "summary", "engagement", "watch", "operations"}
LAYERS = {"domain", "application", "ports", "adapters"}
ALLOWED_LAYERS = {
    "domain": {"domain"},
    "ports": {"domain", "ports"},
    "application": {"domain", "ports", "application"},
    "adapters": LAYERS,
}
VENDOR_MODULES = {
    "aiohttp",
    "discord",
    "fastapi",
    "google",
    "pydantic",
    "sqlite3",
    "uvicorn",
    "websockets",
    "yt_dlp",
}


def _python_files() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _feature_layer(path: Path) -> tuple[str, str] | None:
    relative = path.relative_to(SOURCE_ROOT)
    if len(relative.parts) < 3:
        return None
    context, layer = relative.parts[:2]
    if context in FEATURE_CONTEXTS and layer in LAYERS:
        return context, layer
    return None


def test_context_dependency_direction_is_enforced() -> None:
    violations: list[str] = []
    for path in _python_files():
        source = _feature_layer(path)
        if source is None:
            continue
        source_context, source_layer = source
        for imported in _imports(path):
            parts = imported.split(".")
            if len(parts) < 2 or parts[0] != "discordbot":
                continue
            imported_context = parts[1]
            if imported_context not in FEATURE_CONTEXTS:
                continue
            if imported_context != source_context:
                violations.append(f"{path}: cross-context import {imported}")
                continue
            if len(parts) >= 3 and parts[2] in LAYERS:
                target_layer = parts[2]
                if target_layer not in ALLOWED_LAYERS[source_layer]:
                    violations.append(
                        f"{path}: {source_layer} must not import {target_layer} ({imported})"
                    )
    assert violations == []


def test_frameworks_and_sqlite_stay_behind_adapter_boundaries() -> None:
    violations: list[str] = []
    for path in _python_files():
        layer_info = _feature_layer(path)
        layer = layer_info[1] if layer_info else None
        for imported in _imports(path):
            root = imported.split(".", maxsplit=1)[0]
            if root in VENDOR_MODULES and layer != "adapters":
                violations.append(f"{path}: {imported} is only allowed in adapters")
    assert violations == []


def test_composition_may_only_reach_feature_adapters() -> None:
    violations: list[str] = []
    for path in sorted((SOURCE_ROOT / "composition").rglob("*.py")):
        for imported in _imports(path):
            parts = imported.split(".")
            if len(parts) >= 2 and parts[:1] == ["discordbot"] and parts[1] in FEATURE_CONTEXTS:
                if len(parts) < 3 or parts[2] != "adapters":
                    violations.append(f"{path}: composition import must target adapters: {imported}")
    assert violations == []


def test_only_task_supervisor_can_create_v2_background_tasks() -> None:
    allowed = (SOURCE_ROOT / "platform" / "tasks.py").resolve()
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else ""
            )
            if function_name in {"create_task", "ensure_future"} and path.resolve() != allowed:
                violations.append(f"{path}:{node.lineno}: raw {function_name}")
    assert violations == []


def test_only_bounded_executor_module_can_dispatch_blocking_work() -> None:
    allowed = (SOURCE_ROOT / "platform" / "executors.py").resolve()
    blocked_names = {
        "ProcessPoolExecutor",
        "ThreadPoolExecutor",
        "run_in_executor",
        "to_thread",
    }
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            name = ""
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    name = node.func.id
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.rsplit(".", maxsplit=1)[-1] for alias in node.names]
                if any(candidate in blocked_names for candidate in names):
                    name = next(candidate for candidate in names if candidate in blocked_names)
            if name in blocked_names and path.resolve() != allowed:
                violations.append(f"{path}:{node.lineno}: raw {name}")
    assert violations == []


def test_discord_and_watch_composition_modules_remain_separate() -> None:
    discord_imports = _imports(SOURCE_ROOT / "composition" / "discord_app.py")
    watch_imports = _imports(SOURCE_ROOT / "composition" / "watch_app.py")

    assert all(
        "watch_app" not in imported and ".watch." not in imported
        for imported in discord_imports
    )
    assert all(
        "discord_app" not in imported
        and not any(
            f".{context}." in imported
            for context in {"music", "summary", "engagement"}
        )
        for imported in watch_imports
    )


def test_importing_every_v2_module_has_no_runtime_side_effects() -> None:
    script = f"""
import asyncio
import importlib
import logging
import os
import pkgutil
import socket
import sqlite3
import subprocess
import sys
import threading

sys.path.insert(0, {str(ROOT / 'src')!r})

def forbidden(*args, **kwargs):
    raise AssertionError("runtime side effect during import")

sqlite3.connect = forbidden
socket.socket = forbidden
socket.create_connection = forbidden
subprocess.Popen = forbidden
asyncio.create_task = forbidden
threading.Thread.start = forbidden
os.getenv = forbidden

before_handlers = tuple(logging.getLogger().handlers)
import discordbot
modules = sorted(item.name for item in pkgutil.walk_packages(discordbot.__path__, "discordbot."))
for module in modules:
    importlib.import_module(module)
assert tuple(logging.getLogger().handlers) == before_handlers
print(len(modules))
"""
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) >= 25


@pytest.mark.parametrize(
    "context",
    sorted(FEATURE_CONTEXTS - {"operations"}),
)
def test_feature_context_has_repository_adapter_boundary(context: str) -> None:
    assert (SOURCE_ROOT / context / "ports" / "__init__.py").is_file()
    assert (SOURCE_ROOT / context / "adapters" / "__init__.py").is_file()
