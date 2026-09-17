from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from discordbot.platform.errors import ConflictError
from .test_production_tools import tool

OLD = "r-0000000000000000-0000000000000000"
NEW = "r-1111111111111111-1111111111111111"


@pytest.mark.parametrize("fault", ["approval", "stale", "writer", "timer", "none", "audit_after_switch"])
def test_stopped_activation_guards_and_uncertain_boundary(fault):
    module = tool("production/activate-stopped.py")
    state = {"current": OLD, "locked": False, "switched": False}
    @contextmanager
    def acquire():
        assert not state["locked"]
        state["locked"] = True
        try:
            yield
        finally:
            state["locked"] = False
    def switch(target):
        assert state["locked"]
        state.update(current=target, switched=True)
    def read(args, *_):
        assert state["locked"] and args[:2] == ["systemctl", "show"]
        if "--property=MainPID" in args:
            return "0"
        if ((fault == "writer" and args[2] == "discordbot-staging-discord.service")
                or (fault == "timer" and args[2] == "discordbot-backup.timer")):
            return "active"
        return "inactive"
    def audit(*_):
        if fault == "audit_after_switch" and state["switched"]:
            raise OSError("synthetic full disk")
    store = SimpleNamespace(root=Path("unused"), current=lambda: state["current"], activate=switch,
                            validate=lambda _: {"schema_min": 5, "schema_max": 5})
    args = (store, SimpleNamespace(read=read), SimpleNamespace(write=audit), SimpleNamespace(acquire=acquire),
            NEW, NEW if fault == "stale" else OLD, fault != "approval")
    if fault == "none":
        module.activate(*args)
    else:
        with pytest.raises(OSError if fault == "audit_after_switch" else ConflictError):
            module.activate(*args)
    assert state["current"] == (NEW if fault in {"none", "audit_after_switch"} else OLD)
    assert state["locked"] is False
