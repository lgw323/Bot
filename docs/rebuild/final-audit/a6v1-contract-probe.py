import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from characterization.watch_support import harness, interaction
from discordbot.platform.errors import AuthorizationError, CapacityError, ConflictError, DatabaseUnavailableError, ExternalTemporaryError
from discordbot.watch.adapters.control_client import LoopbackClient
from discordbot.watch.adapters.discord_io import DiscordInteraction
from discordbot.watch.adapters.security import LoopbackAuth
from discordbot.watch.adapters.web import build_public_app
from discordbot.watch.domain.policy import ClosedSession, InvalidCapability
from tests.integration.watch.conftest import Socket
from tests.integration.watch.test_transports import WebSocket, ORIGIN
pytest_plugins = ['tests.integration.watch.conftest']
SECRET='a6v1-synthetic-control-key-32-characters'

@pytest.mark.parametrize('offset,accepted', [(-30,True),(30,True),(-31,False),(31,False)])
def test_auth_exact_time_boundary(offset, accepted):
    auth=LoopbackAuth(SECRET); path='/internal/watch/status'; raw=b'{}'; stamp=str(1000+offset); nonce='a'*32
    args=('127.0.0.1',path,raw,stamp,nonce,auth.signature(path,raw,stamp,nonce),1000)
    if accepted: auth.verify(*args)
    else:
        with pytest.raises(AuthorizationError): auth.verify(*args)

def test_nonce_capacity_replay_and_expiry():
    auth=LoopbackAuth(SECRET); path='/internal/watch/status'; raw=b'{}'
    def verify(i,now):
        nonce=f'{i:032x}'; stamp=str(now)
        auth.verify('127.0.0.1',path,raw,stamp,nonce,auth.signature(path,raw,stamp,nonce),now)
    for i in range(256): verify(i,1000)
    with pytest.raises(AuthorizationError): verify(0,1000)
    with pytest.raises(CapacityError): verify(256,1000)
    verify(256,1061)
    assert len(auth._seen)==1

@pytest.mark.asyncio
@pytest.mark.parametrize('origin', ['',ORIGIN+'/', 'https://other.example.test'])
async def test_websocket_origin_denial(service,invite,origin):
    ws=WebSocket(build_public_app(service,ORIGIN),invite.capability,origin)
    try: assert (await ws.connect())['code']==4003
    finally: await ws.stop()
    assert not service.resolve(invite.capability).peers

@pytest.mark.asyncio
@pytest.mark.parametrize('case,expected', [('origin',403),('csrf',403),('content',400),('extra',400),('nan',400),('path',413),('header',413)])
async def test_public_fail_closed_inputs(service,invite,case,expected):
    headers={'origin':ORIGIN,'x-watch-csrf':'1','content-type':'application/json'}
    body=json.dumps({'video_url':'https://youtu.be/aaaaaaaaaaa','added_by':'Synthetic'})
    path=f'/api/playlist/{invite.capability}/add'
    if case=='origin': headers['origin']=ORIGIN+'/'
    if case=='csrf': headers['x-watch-csrf']='true'
    if case=='content': headers['content-type']='text/plain'
    if case=='extra': body=body[:-1]+',"extra":1}'
    if case=='nan': body=body.replace('"Synthetic"','NaN')
    if case=='path': path+='?x='+'x'*4096
    if case=='header': headers['x-synthetic']='x'*16385
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_public_app(service,ORIGIN)),base_url=ORIGIN) as client:
        result=await client.post(path,content=body,headers=headers)
        assert result.status_code==expected
        assert invite.capability not in result.text and SECRET not in result.text
    assert not await service.resolve(invite.capability).call('playlist')

@pytest.mark.asyncio
async def test_nonce_page_security_and_no_cors(service,invite):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_public_app(service,ORIGIN)),base_url=ORIGIN) as c:
        pages=[await c.get('/watch',params={'session':invite.capability}) for _ in range(2)]
        assert all(x.status_code==200 for x in pages)
        assert pages[0].headers['content-security-policy'] != pages[1].headers['content-security-policy']
        for page in pages:
            assert page.headers['cache-control']=='no-store'
            assert page.headers['x-content-type-options']=='nosniff'
            assert page.headers['referrer-policy']=='no-referrer'
            assert 'access-control-allow-origin' not in page.headers
            assert invite.capability not in page.text

@pytest.mark.asyncio
async def test_invite_order_bind_conflict_and_cleanup_retry(tmp_path):
    async with harness(tmp_path) as h:
        order=[]; create=h.writer.create; bind=h.writer.bind; send=h.channel.send
        async def durable(*a):
            result=await create(*a);order.append('durable');return result
        async def binding(*a):
            await bind(*a);order.append('admin-bind' if a[-2] else 'invite-bind')
        async def admin(**kw):
            order.append('admin-send');return SimpleNamespace(id=600)
        raw=interaction(h.clock)
        async def invite(**kw):
            order.append('invite-send');return SimpleNamespace(id=500,channel=SimpleNamespace(id=1000))
        h.writer.create=durable; h.writer.bind=binding;h.channel.send.side_effect=admin;raw.edit_original_response.side_effect=invite
        await h.controller.request(DiscordInteraction(raw,ORIGIN))
        assert order==['durable','admin-send','admin-bind','invite-send','invite-bind']
        actor=next(iter(h.service.sessions.values()));sid=actor.intent.session_id
        await h.client.call('bind',{'session_id':sid,'channel':1000,'message':500,'admin':False})
        with pytest.raises(ConflictError):
            await h.client.call('bind',{'session_id':sid,'channel':1000,'message':501,'admin':False})
        h.channel.get_partial_message.return_value.delete.side_effect=RuntimeError('synthetic-delete-failure')
        await h.controller.master_close(42,sid)
        assert len((await h.client.call('cleanup',{}))['items'])==1
        assert actor.closed and not h.service.sessions
        h.channel.get_partial_message.return_value.delete.side_effect=None
        await h.controller.cleanup()
        assert (await h.client.call('cleanup',{}))=={'items':[]}
        assert not h.messages.views
        await h.controller.cleanup()

@pytest.mark.asyncio
async def test_failed_durable_close_is_terminal_and_sweep_recovers(service,invite):
    actor,peer=await service.connect(invite.capability,Socket())
    original=service.writer.close
    service.writer.close=AsyncMock(side_effect=DatabaseUnavailableError('synthetic-close-failure'))
    with pytest.raises(DatabaseUnavailableError): await service.close(invite.session_id)
    await asyncio.wait_for(peer.task,1)
    assert actor.closed and not actor.durable_closed and peer.socket.codes==[4001]
    with pytest.raises(InvalidCapability): service.resolve(invite.capability)
    with pytest.raises(ClosedSession): await actor.call('add','https://youtu.be/aaaaaaaaaaa','t','a')
    service.writer.close=original
    await service.sweep()
    assert actor.durable_closed and not service.sessions

@pytest.mark.asyncio
async def test_same_identity_concurrency_and_other_room(service):
    args=(100,42,'concurrent',int(service.now()))
    results=await asyncio.gather(*(service.create(*args) for _ in range(8)))
    assert len({x.capability for x in results})==1 and len(service.sessions)==1
    second=await service.create(200,42,'concurrent',int(service.now()))
    assert second.capability != results[0].capability
    await service.add(results[0].capability,'https://youtu.be/aaaaaaaaaaa','Synthetic')
    assert not await service.resolve(second.capability).call('playlist')
    await service.close(results[0].session_id)
    assert service.resolve(second.capability)

class ResponseTransport:
    def __init__(self,case): self.case=case;self.calls=0
    @asynccontextmanager
    async def post(self,url,data,headers,allow_redirects):
        self.calls+=1;assert not allow_redirects
        value={'correlation':json.loads(data)['correlation'],'data':{'ready':True}}
        status=200
        if self.case=='correlation':value['correlation']='0'*32
        if self.case=='shape':value['data']['ready']='true'
        raw=json.dumps(value).encode()
        if self.case=='duplicate':raw=b'{"correlation":"x","correlation":"y","data":{}}'
        if self.case=='oversized':raw=b'x'*65537
        if self.case=='redirect':status=302
        async def chunks(n):
            for i in range(0,len(raw),n):yield raw[i:i+n]
        yield SimpleNamespace(status=status,content=SimpleNamespace(iter_chunked=chunks))

@pytest.mark.asyncio
@pytest.mark.parametrize('case',['correlation','shape','duplicate','oversized','redirect'])
async def test_client_rejects_hostile_response_without_retry(clock,case):
    transport=ResponseTransport(case);c=LoopbackClient('http://127.0.0.1:9001',SECRET,clock,transport)
    try:
        with pytest.raises(ExternalTemporaryError):await c.call('status',{})
        assert c.active==0 and transport.calls==1
    finally:await c.stop()
