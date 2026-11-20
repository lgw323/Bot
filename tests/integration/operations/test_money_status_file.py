"""In-memory FD/metadata model only; no actual account or status-file access."""
from copy import deepcopy
from pathlib import PurePosixPath
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import posixpath
import stat

import pytest

from discordbot.operations.adapters import money_status_file as reader
from .test_operational_feature_wiring import assembled


ROOT='/run/mymoney-status'
PATH=PurePosixPath(ROOT+'/status.json')


class Filesystem:
    O_RDONLY=0; O_DIRECTORY=1; O_NOFOLLOW=2; O_NONBLOCK=4; O_CLOEXEC=8
    def __init__(self):
        self.nodes={};self.fds={};self.opened=[];self.closed=[];self.reads=0;self.after_read=None
        for n,(name,uid) in enumerate((('/',0),('/run',0),(ROOT,1234)),1):
            self.nodes[name]=self.node(n,stat.S_IFDIR|0o755,uid)
        self.nodes[str(PATH)]=self.node(4,stat.S_IFREG|0o644,1234,b'nonsecret synthetic projection')
    def node(self,ino,mode,uid,raw=b''):
        return {'raw':raw,'meta':dict(st_dev=1,st_ino=ino,st_mode=mode,st_uid=uid,st_gid=1234,
            st_nlink=1,st_size=len(raw),st_mtime_ns=100,st_ctime_ns=100)}
    def name(self,value,dir_fd=None):
        text=str(value).replace('\\','/')
        return posixpath.normpath(text if text.startswith('/') else self.fds[dir_fd][0].rstrip('/')+'/'+text)
    def open(self,value,flags,dir_fd=None):
        name=self.name(value,dir_fd);node=self.nodes.get(name)
        if node is None:raise FileNotFoundError
        assert flags & self.O_NOFOLLOW
        if stat.S_ISLNK(node['meta']['st_mode']):raise OSError('synthetic symlink')
        if flags & self.O_DIRECTORY:assert stat.S_ISDIR(node['meta']['st_mode'])
        fd=10+len(self.opened);self.opened.append(name);self.fds[fd]=(name,node)
        return fd
    def fstat(self,fd):return SimpleNamespace(**self.fds[fd][1]['meta'])
    def stat(self,value,dir_fd=None,follow_symlinks=None):
        assert follow_symlinks is False
        return SimpleNamespace(**self.nodes[self.name(value,dir_fd)]['meta'])
    def read(self,fd,count):
        self.reads+=1;raw=self.fds[fd][1]['raw'][:count]
        if self.after_read:self.after_read()
        return raw
    def close(self,fd):self.closed.append(fd);del self.fds[fd]


def read(monkeypatch,fs):
    monkeypatch.setattr(reader,'os',fs)
    return reader._read_projection(PATH,1234)


def test_exact_public_file_metadata_and_ancestors_are_pinned_and_closed(monkeypatch):
    fs=Filesystem()
    assert read(monkeypatch,fs)==b'nonsecret synthetic projection'
    assert fs.opened==['/','/run',ROOT,str(PATH)]
    assert len(fs.closed)==4 and not fs.fds


@pytest.mark.parametrize('field,bad',[('st_uid',0),('st_uid',999),('st_nlink',2),
    ('st_mode',stat.S_IFREG|0o600),('st_mode',stat.S_IFREG|0o666),
    ('st_mode',stat.S_IFLNK|0o644),('st_mode',stat.S_IFIFO|0o644),('st_size',0),('st_size',2049)])
def test_untrusted_owner_permissions_links_type_or_size_never_read_payload(monkeypatch,field,bad):
    fs=Filesystem();fs.nodes[str(PATH)]['meta'][field]=bad
    assert read(monkeypatch,fs) is None
    assert fs.reads==0 and not fs.fds


@pytest.mark.parametrize('path,field,bad',[
    ('/run','st_mode',stat.S_IFDIR|0o775),('/run','st_uid',1234),
    (ROOT,'st_mode',stat.S_IFDIR|0o777),(ROOT,'st_mode',stat.S_IFDIR|0o700),
    (ROOT,'st_mode',stat.S_IFLNK|0o755),(ROOT,'st_uid',0)])
def test_writable_untrusted_or_wrong_runtime_ancestor_is_refused(monkeypatch,path,field,bad):
    fs=Filesystem();fs.nodes[path]['meta'][field]=bad
    assert read(monkeypatch,fs) is None
    assert fs.reads==0 and not fs.fds


@pytest.mark.parametrize('race',['rename','mtime','ctime','size','ancestor'])
def test_file_and_ancestor_identity_changes_during_read_are_not_published(monkeypatch,race):
    fs=Filesystem()
    def change():
        if race in ('rename','ancestor'):
            name=str(PATH) if race=='rename' else ROOT
            fs.nodes[name]=deepcopy(fs.nodes[name]);fs.nodes[name]['meta']['st_ino']=99
        else:fs.nodes[str(PATH)]['meta']['st_'+race+('_ns' if race in ('mtime','ctime') else '')]+=1
    fs.after_read=change
    assert read(monkeypatch,fs) is None
    assert not fs.fds


def test_short_payload_read_or_permission_error_is_unknown(monkeypatch):
    for failure in ('short','denied'):
        fs=Filesystem()
        if failure=='short':fs.read=Mock(return_value=b'')
        else:fs.open=Mock(side_effect=PermissionError('PRIVATE'))
        assert read(monkeypatch,fs) is None
        assert not fs.fds


def test_windows_or_absent_identity_never_attempts_any_projection_path(monkeypatch):
    lookup=Mock(side_effect=KeyError('no synthetic identity'))
    access=Mock(side_effect=AssertionError('no file access expected'))
    monkeypatch.setattr(reader,'sys',SimpleNamespace(platform='win32'))
    monkeypatch.setattr(reader,'_owner_uid',lookup);monkeypatch.setattr(reader,'_read_projection',access)
    assert reader.read_fixed_projection() is None
    lookup.assert_not_called()
    monkeypatch.setattr(reader,'sys',SimpleNamespace(platform='linux'))
    assert reader.read_fixed_projection() is None
    access.assert_not_called()


@pytest.mark.asyncio
async def test_async_provider_has_no_path_argument_and_only_uses_existing_executor():
    executor=SimpleNamespace(run=AsyncMock(return_value=None))
    assert await reader.FixedMoneyStatus(executor).snapshot() is None
    executor.run.assert_awaited_once_with(reader.read_fixed_projection)


@pytest.mark.asyncio
async def test_current_service_panel_does_not_open_the_retired_financial_projection(assembled):
    _, feature, _, calls, _ = assembled
    await feature.start()
    try:
        assert 'money_status' not in calls['panel'][1]
        assert 'services' in calls['panel'][1]
    finally:
        await feature.stop()
