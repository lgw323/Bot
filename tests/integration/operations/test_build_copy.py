"""Synthetic file operations only; runnable with stdlib unittest on local Linux."""
import errno
import json
import logging
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
import zipfile

from discordbot.operations.adapters import build
from discordbot.operations.adapters.filesystem import ReleaseStore, digest
from discordbot.platform.errors import DataIntegrityError


class BuildCopyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="build-copy-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "lib"
        self.source.mkdir()
        self.alias = self.root / "lib64"

    def copy(self):
        build.materialize_library(self.source, self.alias)

    def test_regular_contents_and_empty_directories(self):
        (self.source / "empty").mkdir()
        (self.source / "module").write_bytes(b"synthetic\x00payload")
        self.copy()
        self.assertEqual(digest(self.source / "module"), digest(self.alias / "module"))
        self.assertTrue((self.alias / "empty").is_dir())

    @unittest.skipIf(os.name == "nt", "POSIX mode semantics")
    def test_ordinary_modes_and_timestamps_preserved_without_special_bits(self):
        self.source.chmod(0o2700)
        (self.source / "nested").mkdir()
        (self.source / "nested").chmod(0o2750)
        for mode in (0o640, 0o751, 0o4751, 0o2640, 0o1640):
            path = self.source / str(mode)
            path.write_bytes(b"synthetic")
            path.chmod(mode)
            os.utime(path, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_001))
        self.copy()
        for path in [self.source, *self.source.rglob("*")]:
            target = self.alias / path.relative_to(self.source)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), stat.S_IMODE(path.stat().st_mode) & 0o777)
            self.assertEqual(target.stat().st_mtime_ns, path.stat().st_mtime_ns)

    def test_existing_destination_is_not_merged_or_overwritten(self):
        self.alias.mkdir()
        sentinel = self.alias / "sentinel"
        sentinel.write_bytes(b"preserve")
        with self.assertRaises(FileExistsError):
            self.copy()
        self.assertEqual(sentinel.read_bytes(), b"preserve")

    @unittest.skipIf(os.name == "nt", "real POSIX links")
    def test_nested_links_rejected_without_copying_target(self):
        outside = self.root / "outside"
        outside.write_bytes(b"private-canary")
        (self.source / "link").symlink_to(outside)
        with self.assertRaises(DataIntegrityError):
            self.copy()
        self.assertFalse((self.alias / "link").exists())
        self.assertEqual(outside.read_bytes(), b"private-canary")

    @unittest.skipIf(os.name == "nt", "real POSIX special files")
    def test_fifo_rejected_before_read(self):
        os.mkfifo(self.source / "pipe")
        with self.assertRaises(DataIntegrityError):
            self.copy()
        self.assertFalse((self.alias / "pipe").exists())

    @unittest.skipIf(os.name == "nt" or getattr(os, "geteuid", lambda: 0)() == 0, "POSIX unprivileged access")
    def test_real_read_error_is_not_ignored(self):
        path = self.source / "unreadable"
        path.write_bytes(b"synthetic")
        path.chmod(0)
        self.addCleanup(path.chmod, 0o600)
        with self.assertRaises(PermissionError):
            self.copy()

    def test_nested_aggregate_diagnostic_is_bounded_and_redacted(self):
        canary = "PRIVATE_TOKEN_URL_USER"
        inner = shutil.Error([(str(self.source / canary), str(self.alias / canary),
                               "[Errno 1] " + canary)] * 40)
        outer = shutil.Error([(canary, canary, inner)])
        result = build.copy_failure_details(outer, self.source, self.alias)
        self.assertNotIn(canary, json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["errors"]), 16)
        self.assertTrue(any(row["errno"] == errno.EPERM and row["source"] == "venv_library"
                            and row["destination"] == "venv_alias" for row in result["errors"]))
        self.assertLess(len(json.dumps(result)), 4096)

    def test_malformed_cycles_and_unknown_errno_cannot_export_messages(self):
        canary = "PRIVATE_TOKEN_URL_USER"
        outer = shutil.Error([])
        outer.args[0].extend([(canary, canary, outer), (canary, canary, "[Errno 99999] " + canary), canary])
        outer.__cause__ = outer
        result = build.copy_failure_details(outer, self.source, self.alias)
        self.assertNotIn(canary, json.dumps(result))
        self.assertNotIn("99999", json.dumps(result))
        self.assertTrue(result["truncated"])

    def builder(self, runner):
        source, wheels, store_root = (self.root / name for name in ("source", "wheels", "store"))
        for path in (source / "src", source / "tests", source / "deploy", wheels, store_root / "releases"):
            path.mkdir(parents=True)
        pins = source / "deploy/dependencies.pins"
        pins.write_text("example==1.0\n")
        with zipfile.ZipFile(wheels / "example-1.0-py3-none-any.whl", "w") as archive:
            archive.writestr("example-1.0.dist-info/METADATA", "Name: example\nVersion: 1.0\n")
        build.seal_wheels(wheels, pins)
        return build.Builder(ReleaseStore(store_root), runner, source, wheels)

    def test_builder_reports_aggregate_preserves_exception_and_cleanup(self):
        canary = "PRIVATE_TOKEN_URL_USER"
        failure = shutil.Error([(canary, canary, "[Errno 13] " + canary)])
        class FailingRunner:
            def run(self, args, cwd, timeout):
                raise failure
        builder = self.builder(FailingRunner())
        with self.assertLogs(build.__name__, level="WARNING") as captured:
            with self.assertRaises(shutil.Error) as caught:
                builder.build("a" * 40)
        self.assertIs(caught.exception, failure)
        self.assertFalse(list(builder.store.releases.iterdir()))
        self.assertNotIn(canary, " ".join(captured.output))
        self.assertIn("permission_denied", " ".join(captured.output))
        self.assertEqual(captured.records[0].event, "build.filesystem_failed")
        self.assertEqual(captured.records[0].fields["failure"]["errors"][0]["errno"], errno.EACCES)

    def test_diagnostic_sink_failure_cannot_replace_exception_or_skip_cleanup(self):
        failure = PermissionError(errno.EACCES, "synthetic failure")
        class FailingRunner:
            def run(self, args, cwd, timeout):
                raise failure
        class BrokenHandler(logging.Handler):
            def emit(self, record):
                raise RuntimeError("synthetic logging failure")
        builder = self.builder(FailingRunner())
        handler = BrokenHandler()
        build.logger.addHandler(handler)
        self.addCleanup(build.logger.removeHandler, handler)
        with self.assertRaises(PermissionError) as caught:
            builder.build("a" * 40)
        self.assertIs(caught.exception, failure)
        self.assertFalse(list(builder.store.releases.iterdir()))

    @unittest.skipIf(os.name == "nt", "real POSIX venv alias")
    def test_actual_builder_materializes_only_known_alias_and_inventories_hashes(self):
        class Runner:
            def run(self, args, cwd, timeout):
                if args[1:3] == ["-m", "venv"]:
                    venv = Path(args[-1])
                    (venv / "lib").mkdir(parents=True)
                    (venv / "lib/module").write_bytes(b"payload")
                    (venv / "lib64").symlink_to("lib", target_is_directory=True)
        builder = self.builder(Runner())
        path = builder.store.path(builder.build("a" * 40))
        value = json.loads((path / "candidate.json").read_text())
        self.assertFalse((path / ".venv/lib64").is_symlink())
        self.assertEqual(value["files"][".venv/lib/module"], value["files"][".venv/lib64/module"])
        self.assertTrue((path / ".building").is_file())
        self.assertFalse((path / "manifest.json").exists())

    @unittest.skipIf(os.name == "nt", "real POSIX venv alias")
    def test_actual_builder_rejects_external_alias_and_retains_unsafe_tree(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep").write_bytes(b"preserve")
        class Runner:
            def run(self, args, cwd, timeout):
                if args[1:3] == ["-m", "venv"]:
                    venv = Path(args[-1])
                    (venv / "lib").mkdir(parents=True)
                    (venv / "lib64").symlink_to(outside, target_is_directory=True)
        builder = self.builder(Runner())
        with self.assertRaises(DataIntegrityError):
            builder.build("a" * 40)
        # Existing ReleaseStore cleanup refuses trees containing any link.
        # Preserve that fail-closed behavior rather than traversing the target.
        retained = list(builder.store.releases.iterdir())
        self.assertEqual(len(retained), 1)
        self.assertTrue((retained[0] / ".building").is_file())
        self.assertFalse((retained[0] / "candidate.json").exists())
        self.assertEqual((outside / "keep").read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
