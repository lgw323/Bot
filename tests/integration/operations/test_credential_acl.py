import stat
import struct

import pytest

from discordbot.operations.adapters.configuration import private_mode
from discordbot.platform.errors import ConfigurationError


def credential_acl(*, uid=997, group=0, other=0, mask=4, named=4):
    entries = [(1, 4, 0xFFFFFFFF), (2, named, uid), (4, group, 0xFFFFFFFF),
               (16, mask, 0xFFFFFFFF), (32, other, 0xFFFFFFFF)]
    return struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in entries)


def test_systemd_root_owned_credential_grants_only_service_uid_read():
    private_mode(stat.S_IFREG | 0o440, 0, 997, credential_acl())


@pytest.mark.parametrize("acl", [credential_acl(uid=998), credential_acl(group=4),
    credential_acl(other=4), credential_acl(mask=6), credential_acl(named=6),
    credential_acl() + struct.pack("<HHI", 2, 4, 999), b"malformed", None])
def test_credential_acl_never_accepts_extra_readers_writers_or_invalid_metadata(acl):
    with pytest.raises(ConfigurationError):
        private_mode(stat.S_IFREG | 0o440, 0, 997, acl)


def test_acl_exception_does_not_apply_to_writable_or_nonroot_credentials():
    for mode, owner in [(0o640, 0), (0o440, 997), (0o444, 0)]:
        with pytest.raises(ConfigurationError):
            private_mode(stat.S_IFREG | mode, owner, 997, credential_acl())
