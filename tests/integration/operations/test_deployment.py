from contextlib import contextmanager

import pytest

from discordbot.operations.application.deployment import Deployment
from discordbot.operations.ports.deployment import Release


class Fake:
    def __init__(self, fail=None, initial=False, rollback_fail=False):
        self.calls = []
        self.fail, self.rollback_fail = fail, rollback_fail
        self.pointer = None if initial else Release("old")
        self.locked = False
        self.failed = False

    @contextmanager
    def lock(self):
        assert not self.locked
        self.locked = True
        try:
            yield
        finally:
            self.locked = False

    def current(self):
        return self.pointer

    def call(self, name):
        self.calls.append(name)
        if name == self.fail and not self.failed:
            self.failed = True
            raise RuntimeError("injected")
        if self.rollback_fail and self.failed and name == "ready:old":
            raise RuntimeError("rollback")

    def build(self, revision):
        self.call("build")
        return Release("new")

    def activate(self, release):
        self.call("activate:" + release.identity)
        self.pointer = release

    def stop(self): self.call("stop")
    def start(self): self.call("start")
    def preflight(self, release): self.call("preflight:" + release.identity)
    def test(self, release): self.call("test:" + release.identity)
    def compatible(self, release): self.call("compatible:" + release.identity)
    def backup(self, release): self.call("backup:" + release.identity)
    def publish(self, release): self.call("publish:" + release.identity)
    def ready(self, release): self.call("ready:" + release.identity)
    def smoke(self, release): self.call("smoke:" + release.identity)
    def retain(self, release, previous): self.call("retain")
    def discard(self, release): self.call("discard")
    def audit(self, operation, release, result, reason): self.call(f"audit:{operation}:{result}")


@pytest.mark.parametrize("initial", [True, False])
def test_success_order(initial):
    fake = Fake(initial=initial)
    assert Deployment(fake).run("revision").result == "ok"
    assert fake.calls.index("backup:new") < fake.calls.index("publish:new") < fake.calls.index("stop")
    assert fake.calls.index("activate:new") < fake.calls.index("ready:new") < fake.calls.index("smoke:new")
    assert fake.pointer.identity == "new"
    assert not fake.locked


@pytest.mark.parametrize("stage", ["build", "preflight:new", "test:new", "compatible:new", "backup:new", "publish:new"])
def test_pre_activation_failure_preserves_pair(stage):
    fake = Fake(stage)
    outcome = Deployment(fake).run("revision")
    assert outcome.result == "failed" and outcome.rollback == "not_needed"
    assert fake.pointer.identity == "old"
    assert "stop" not in fake.calls and not fake.locked


@pytest.mark.parametrize("stage", ["stop", "activate:new", "start", "ready:new", "smoke:new", "audit:deployment:ok"])
def test_failure_rolls_back_code_and_dependency_pair(stage):
    fake = Fake(stage)
    outcome = Deployment(fake).run("revision")
    assert outcome.result == "failed" and outcome.rollback == "ok"
    assert fake.pointer.identity == "old"
    assert "compatible:old" in fake.calls and "ready:old" in fake.calls
    assert not fake.locked


def test_failed_rollback_stops_pair_and_is_visible():
    fake = Fake("ready:new", rollback_fail=True)
    assert Deployment(fake).run("revision").rollback == "failed"
    assert fake.calls.count("activate:old") == 1
    assert fake.calls[-2] == "stop"


def test_initial_failure_has_no_fictitious_rollback():
    fake = Fake("ready:new", initial=True)
    assert Deployment(fake).run("revision").rollback == "no_previous_stopped"


def test_cancel_during_switch_restores_old_pair():
    fake = Fake()
    activate = fake.activate
    def cancel(release):
        activate(release)
        if release.identity == "new":
            raise KeyboardInterrupt
    fake.activate = cancel
    with pytest.raises(KeyboardInterrupt):
        Deployment(fake).run("revision")
    assert fake.pointer.identity == "old" and not fake.locked


def test_audit_failure_before_build_has_no_mutation():
    fake = Fake("audit:deployment:started")
    with pytest.raises(RuntimeError):
        Deployment(fake).run("revision")
    assert "build" not in fake.calls and not fake.locked
