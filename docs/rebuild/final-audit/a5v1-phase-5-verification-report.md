# A5V1 - Independent Phase 5 verification

2026-10-02. **PHASE 5 PASS. A5-M1 independently CLOSED.**
No new MATERIAL, required DRIFT or BLOCKED finding. This is the current repository's
scoped synthetic contract verdict, not deployment approval or a new live verification.
STOP A5V1 for parent review. No A6, Integrated Audit or Phase 11 is started.

## Authority and target

Entry/evidence HEAD `34416e13a11f3ef4db7e94c2e31b6435a838352f`, branch
`codex/rebuild-v2`; implementation `40db561f95b01408139430829d374b1e39c5d95c`.
Read active-state, ledger and document index first, then C7, ADR-020, C1/C2,
F006-F010 / FR-026-030, B20 Phase 5, scoped NFR/product/trace, original Phase 5
report, A5 FAIL/report/unchanged probe, A5R1, repository AGENTS and current code/tests.
Parent's explicit A5V1 assignment supersedes old NEXT text only in this scope.
No specialized artifact/app skill applies to this repository code audit.

Reviewed capture, service, models, ports, Discord I/O/UI, Gemini, runtime, composition
and assertions/fixture isolation. Root conftest disables dotenv and denies credential
reads; synthetic harnesses supply capture, clocks, authorization and provider. Legacy
characterization mocks Gemini and supplies synthetic conversation. HTTP uses fake
sessions; Discord calls use AsyncMock. No production data, network request, installation
or WSL was needed. No implementation or repository test was edited.

## Independent A5-M1 closure and combined faults

Extracted the original A5 Python appendix verbatim; no assertion, synchronization,
parameter or skip changes. Both successful and failed cancellation notices now produce
`propagated=True`, `cancelled=True`, `cancelling=1`, `done=True`. The same unchanged
probe asserts provider cancellation, empty supervisor/reservations/results/views,
exactly one private send and no raw delivery error in telemetry before cancellation.

The six-line A5R1 adapter delta catches only ResponderFailure within the cancellation
handler, emits the existing fixed delivery-failure event, then re-raises the original
CancelledError. It does not add retry, broaden ordinary error handling or change UI.
Fresh repair regressions cover native cancellation / deadline / provider failure crossed
with success / failed notice / actual two-second notice timeout, second cancellation
inside notice and completed-result handoff. All 11 pass independently.

New probes additionally cancel or expire a queued controller with both notice outcomes
while another request remains active and three waiters are retained. The released slot
accepts a replacement; provider order is exactly active, 0, 1, 2, replacement. No provider
call is made for the cancelled/expired waiter. Cancellation during uncertain defer or
public-send propagates without retry; completed unbound results and views are reclaimed.
Real SummaryResource shutdown cancels simultaneous provider and reconciliation work,
closes existing View/Modal and provider/bot, clears capture/results and both supervisors,
and propagates controller cancellation even when its private notice fails.

## Fresh executed evidence (disjoint counts)

Existing Windows Python 3.12 `.venv`; `PYTHON_DOTENV_DISABLED=1`,
`PYTHONIOENCODING=utf-8`; RuntimeWarning and PytestUnraisableExceptionWarning are errors.

| Selection | PASS | FAIL | SKIP / XFAIL | Receipt |
| --- | ---: | ---: | ---: | --- |
| Unchanged A5 original probe | 2 | 0 | 0 / 0 | 0.61s; both cancellation observations true |
| A5R1 cancellation_delivery file | 11 | 0 | 0 / 0 | 6.08s; includes real 2-second Discord timeout |
| Remaining Summary integration + Summary/component characterization, explicitly excluding above file | 85 | 0 | 0 / 0 | 1.54s |
| New independent appendix, first 21 cases | 21 | 0 | 0 / 0 | 0.98s |
| Three appended source/shutdown cases only | 3 | 0 | 0 / 0 | 0.87s; 21 deselected, not counted again |
| Architecture import rules + two Summary nested-cleanup consumers | 14 | 0 | 0 / 0 | 1.12s; 12 architecture + 2 Summary |
| **Disjoint total** | **136** | **0** | **0 / 0** | No historical counts added |

An initial attempt to collect the TEMP original probe and a repository test together
without --confcutdir failed collection: pytest traversed an inaccessible Windows
`Temporary Internet Files` junction. No tests ran in that invocation. The probe was then
run separately with --confcutdir TEMP, and the regression file separately from the repo.
This launcher/collection error is disclosed, not a product failure or hidden passing run.
The extra architecture selection is justified by C7 import/layer/lifecycle gates and
later composition changes; no broad functional or full-suite run was needed or claimed.

Exact successful commands (repository root; each has the strict warning flags above):

```powershell
.venv/Scripts/python.exe -m pytest "$env:TEMP/discordbot-a5v1-original.py" -c pyproject.toml --confcutdir $env:TEMP -q -s -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe -m pytest tests/integration/summary/test_cancellation_delivery.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe -m pytest tests/integration/summary/ tests/characterization/test_summary_contracts.py tests/characterization/test_component_contracts.py::test_f009_f010_fr028_fr029_preserve_summary_components tests/characterization/test_component_contracts.py::test_f010_fr029_correct_summary_topics_paginate_with_stable_ids --ignore=tests/integration/summary/test_cancellation_delivery.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe -m pytest "$env:TEMP/discordbot-a5v1-independent.py" -c pyproject.toml --confcutdir $env:TEMP -q -x -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe -m pytest "$env:TEMP/discordbot-a5v1-independent.py" -c pyproject.toml --confcutdir $env:TEMP -q -x -k 'one_failed_source or real_resource_stop' -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
.venv/Scripts/python.exe -m pytest tests/architecture/test_import_rules.py 'tests/integration/watch/test_cleanup_ownership.py::test_equivalent_nested_report_consumers_preserve_dependencies[summary-service]' 'tests/integration/watch/test_cleanup_ownership.py::test_equivalent_nested_report_consumers_preserve_dependencies[summary-resource]' -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

The fourth command ran before the final three appendix cases were appended. To reproduce
its exact 21-case selection from the final appendix, add
`-k 'not one_failed_source and not real_resource_stop'`. The fifth command selects the
remaining three. Alternatively run the complete final appendix once for 24 cases;
that alternative run is not an additional receipt claimed here. Original probe source
remains in [A5 report](a5-phase-5-report.md#exact-synthetic-reproducer).

## Complete Phase 5 gate disposition

All PASS below are repository contract evidence; explicit deployment/live exclusions
are listed separately. Static numeric/config checks supplement executable boundaries.

| Gate / authority | Current evidence and disposition |
| --- | --- |
| F006 / FR-026 capture and restart reconciliation; CF-16 | PASS: `test_capture` covers live/preload interleave, ID ordering/dedupe, first observation, bounded reverse cursor, failed retry, initial 3h/reconnect 24h and age-before-count. `test_lifecycle` covers ready/resumed coalescing, no edit/delete listeners and late-ready no restart. New source-failure case proves independent ready states and refusal of incomplete source. Current adapters reject DM/bot/empty/unconfigured input. Restart uses current Discord history; deleted/out-of-retention recovery is not promised. |
| F007 retention/capacity/disabled | PASS: finite immutable config, one source/guild <=10, <=1000/source, <=100/page, body<=4000/name<=100; read/add prune and bounded cleanup. Existing retention/disabled/config cases plus new 1100-message input retain newest 1000; prompt uses newest complete JSON rows <=100000 characters in chronological order. No durable DB/schema or raw user ID capture. |
| F008 / FR-027 basic UI; CF-19 | PASS: real command signature `/요약 hours:number=6.0`, public thinking defer/embed, overview/numbering/requester/token/time, private no-data/error and safe text. Existing golden V1 shell and current V2 assertions both run. Max normal field/overview pages remain <=25 fields and <=6000 characters. |
| F009 / FR-028 advanced | PASS: original three labels, 300-second modal, per-field 1000-character validation, finite hours within retention, inherited hours, keyword substring OR/user exact OR/case-insensitive AND between groups. User preference is data, never interpolated in system instructions. Original date-picker inventory wording is corrected by C7/ADR, not an omitted new UI. |
| F010 / FR-029 refresh/detail/page | PASS: fresh public result keeps query and old immutable result; bound guild/destination/message and token:absolute-index checks. Existing invalid/stale/expiry and 26th-topic cases; new all 100 topics accessible across four pages by a different authorized user, all details private, old result still usable after refresh. Result/View <=32 and Modal <=32, expiry/eviction/stop checks pass. |
| FR-030 ACL/privacy | PASS: source view/history and member cache fail closed; before queue, after queue, immediately before provider and after provider. Existing queued revocation and cross-context tests; new missing channel/guild/member/wrong-guild checks, revocation during provider, all five component/modal entrypoints deny before provider or UI disclosure. Prompt scope/name/time/body only, safe class-owned errors, allowlisted telemetry and secret-in-header/never-URL verified. Destination ACL alignment remains live deployment responsibility per C7/ADR-020. |
| Gemini adapter limits / CF-09 | PASS: lazy aiohttp/fixed TLS endpoint, no redirects, one request/zero retry, total/connect/read min(60/10/30, remaining), <=512000 response bytes, STOP/JSON/field/topic bounds and typed failures. Existing parser/status/size/diagnostic cases plus independent streaming cancellation/timeout/OSError close the response context, propagate safe typed outcomes and close session once. New .5-second budget reaches all transport bounds. |
| FIFO/admission/deadline / CF-08/09 | PASS: active1/waiting4, sixth rejection, early/waiter/active cancel, timeout and provider errors release capacity; 60-second absolute budget includes queue/ACL, 59.999 success and 60/61 late-result rejection, queue50 leaves10. Independent queue-fault replacement proves FIFO recovery under failed notice. Existing unrelated async/capture progress remains passing; no thread/executor sharing. |
| Response and cancellation / CF-19 / A5-M1 | PASS, M1 CLOSED: original exact 2-case reproducer, 11 repair regressions and independent queued/pre-ACK/public-send/resource-stop interleavings; one private response when possible, uncertain send never retried, no raw failure text. Deadline/provider errors retain ordinary safe completion; native cancellation retains native control flow. |
| Lifecycle / CF-16/20 / C3 | PASS: separate request/background supervisors, finite limits, normal resource cleanup, disabled no startup, owned-bot close, late-ready no resurrection. New real resource stop tests close both task sets, UI, raw capture/results and provider. Two focused later-cleanup consumers refuse dependency close for incomplete shutdown. Failed cleanup remains terminal under A2 containment, not newly promised automatic retry. |
| Architecture / NFR / later wiring | PASS: all 12 existing import/layer/task/executor checks, including fresh-process import with DB/socket/process/thread/task/env side effects forbidden. Current `production_discord.py` explicitly composes Summary from main-channel mappings and Gemini config; standalone builder remains lazy. No inward SDK/DB or dead alternate V2 route supersedes audited service/controller. V1 paths remain legacy compatibility, not current production composition. |
| Historical accuracy / trace | Original Phase 5 counts and staged risks remain historical. A5-M1 exposed an originally untested combined fault; A5V1 closes that gap without rewriting historical claims. Phase 5 no-production-wiring wording describes its original implementation stage; later composition is intentional, not a new unauthorized scope change. P2 gate6 human success/request1 telemetry only supports that historical release. |

## History, evidence limits and unchanged production

Original core `c81f4d1` and adapter `643b75a` establish the audited ownership. Later
`868cea7` added allowlisted provider diagnostics, `d042e5e` propagated nested cleanup,
and `40db561` repairs cancellation feedback. The present review and tests include those
paths instead of assuming Phase 5's old PASS or A5R1's 98 count proves current safety.

No fresh live Discord Gateway/cache/intents/ACK, source-to-result channel permission
alignment, Gemini model/REST support, summary quality/availability, actual HTTP timing,
Pi capacity or soak verification. Cooperative provider cancellation is the explicit port
contract; arbitrary cancellation-resistant providers are outside the finite-close claim.
No clean full-suite claim: known document-inventory and Deno failures, inherited audioop
deprecation, A3-N1 MINOR and A3-I1 INFO remain disclosed and unchanged. No new finding ID
is assigned. B20/C7 phase exit requires synthetic/golden/fault proof; the stated live
checks belong to deployment gates, so their absence is not converted into a live PASS.

Production was not accessed. Recorded source `8e9018d4b8061cde6006eee47fa4103522f77718`
and pin `r-8e9018d4b8061cde-3dac82a792fad576` remain separate and unchanged. No real
conversation transmission, external AI request, Discord send, charges, credential or
permission changes, DB read/write/restore, Pi access/deploy/restart, systemd/Cloudflare,
V1, concurrent writer or cleanup. Friend activation HELD; final Integrated Audit
condition unmet; MyFood paused. A0-A4 PASS unchanged; A6-A10 remain NOT_AUDITED.

## Ownership, local commit and rollback

[Entry inventory](a5v1-entry-inventory.json): exact 11 modified / 59 untracked files,
70 hashes, empty index. All 70 matched immediately before owned authority edits.
The inherited paths/statuses are exhaustively listed there. Inherited modified files:
CHANGELOG, README, product-spec, rebuild README, current-plan, active-state, ledger,
A3 report, full-sweep report, Phase 10 report and browser/watch_fixture.py. The 59
untracked files include the mixed document index/A5 navigation, Phase 10B evidence,
A0-A2 reports, gpt_handoff export/zip, server invite guide and browser scripts.

Owned records only: this report/embedded probe, entry inventory, active-state AO append,
Phase 5 ledger replacement and document-index A5V1 append. Commit only new report and
inventory plus AO/Phase 5 row against HEAD; inherited mixed authority and index content
remain uncommitted. The complete appendix is retained as audit evidence, not installed
as a repository test or product fix. Exact final local SHA is reported at handoff;
staged diff and `git diff --cached --check` are reviewed before commit. No remote push.
Preservation check removes only these three owned authority/navigation deltas and
compares all 70 original byte hashes. Expected residual: 11 modified / 59 untracked,
empty index. Temporary synthetic probe files remain in TEMP as audit aids, not staged.

Rollback: revert only the A5V1 audit commit after review; remove only its separately
owned uncommitted navigation appendix if requested. Preserve the inherited 70 files,
A5/A5R1 history and implementation. No data restore or history rewrite.

**STOP A5V1. Next narrow boundary: parent review of this independent Phase 5 PASS.**
A6 requires a separate explicit assignment; no automatic continuation or deployment.

## Exact independent synthetic appendix

Save this block as `$env:TEMP/discordbot-a5v1-independent.py`. It installs the root
credential guard and supplies only synthetic/mocked providers and Discord I/O.
UTF-8 source (no BOM), SHA-256:
`9f3117d3c4ab4fe5a78e49c9d450e240b1009a6133291bdad719a7b4bdf80dc7`.

```python
"""A5V1 independent synthetic contract challenges; no runtime/test edits."""
import asyncio
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

ROOT = Path.cwd()
runpy.run_path(str(ROOT / 'conftest.py'))
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from characterization.summary_support import harness, interaction, settled
from discordbot.platform.errors import AuthorizationError, CancellationError, DeadlineExceededError, ExternalTemporaryError
from discordbot.summary.adapters.discord_io import DiscordAuthorization
from discordbot.summary.adapters.discord_ui import SummaryController
from discordbot.summary.adapters.gemini import GeminiProvider
from discordbot.summary.domain.models import Message, Prompt, Query, Scope, Summary, Topic

@pytest_asyncio.fixture
async def fx():
    f = harness()
    c = SummaryController(f.service)
    try:
        yield f, c
    finally:
        c.close()
        await f.service.stop()

@pytest.mark.asyncio
@pytest.mark.parametrize('trigger', ['cancel', 'deadline'])
@pytest.mark.parametrize('send_fails', [False, True])
async def test_queued_fault_releases_slot_and_preserves_active_fifo(fx, trigger, send_fails):
    f, c = fx
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def provider(prompt, **kwargs):
        calls.append(json.loads(prompt.data)['preference'])
        if len(calls) == 1:
            entered.set()
            await release.wait()
        return Summary('synthetic', (Topic('synthetic'),))
    f.provider.generate.side_effect = provider
    active = f.service.submit(100, 300, 200, Query(extra='active'))
    await asyncio.wait_for(entered.wait(), 1)
    req = interaction()
    if send_fails:
        req.followup.send.side_effect = RuntimeError('PRIVATE_NOTICE')
    queued = asyncio.create_task(c.execute(req, Query(extra='cancelled')))
    successors = []
    try:
        await settled()
        assert f.service.waiting == 1
        successors = [f.service.submit(100, 301, 200, Query(extra=str(i))) for i in range(3)]
        assert f.service.waiting == 4
        if trigger == 'cancel':
            queued.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(queued, 1)
        else:
            f.timers.expire(1)  # first service, then queued controller timer
            await asyncio.wait_for(queued, 1)
        await settled()
        assert not active.done() and f.service.waiting == 3
        successors.append(f.service.submit(100, 301, 200, Query(extra='replacement')))
        release.set()
        await asyncio.wait_for(asyncio.gather(active, *successors), 1)
        await settled()
        assert calls == ['active', '0', '1', '2', 'replacement']
        assert f.service.active == f.service.waiting == 0
        req.followup.send.assert_awaited_once()
        expected = CancellationError if trigger == 'cancel' else DeadlineExceededError
        assert req.followup.send.call_args.kwargs == dict(wait=True, content=expected.default_safe_message, ephemeral=True)
        assert 'PRIVATE' not in repr(f.buffer.drain())
    finally:
        release.set()
        for task in [active, queued, *successors]:
            if not task.done(): task.cancel()
        await asyncio.gather(active, queued, *successors, return_exceptions=True)

@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['defer', 'public_send'])
async def test_cancellation_during_uncertain_delivery_does_not_retry(fx, stage):
    f, c = fx
    req = interaction()
    entered, finished = asyncio.Event(), asyncio.Event()
    async def stall(**kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()
    target = req.response.defer if stage == 'defer' else req.followup.send
    target.side_effect = stall
    task = asyncio.create_task(c.execute(req, Query()))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await asyncio.wait_for(task, 1)
        await settled()
        target.assert_awaited_once()
        assert finished.is_set() and not f.service._results and not c._views
        assert f.service.active == 0 and not f.supervisor.snapshot().active
        assert req.followup.send.await_count == (stage == 'public_send')
        req.response.send_message.assert_not_awaited()
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)

@pytest.mark.asyncio
@pytest.mark.parametrize('missing', ['channel', 'guild', 'member', 'wrong_guild'])
async def test_actual_acl_cache_fail_closed(missing):
    member = object()
    channel = SimpleNamespace(guild=SimpleNamespace(id=101 if missing == 'wrong_guild' else 100),
        permissions_for=MagicMock(return_value=SimpleNamespace(view_channel=True, read_message_history=True)))
    guild = SimpleNamespace(get_member=MagicMock(return_value=None if missing == 'member' else member))
    bot = SimpleNamespace(get_channel=MagicMock(return_value=None if missing == 'channel' else channel),
        get_guild=MagicMock(return_value=None if missing == 'guild' else guild))
    with pytest.raises(AuthorizationError): await DiscordAuthorization(bot).require(Scope(100,200),300)
    channel.permissions_for.assert_not_called()

@pytest.mark.asyncio
async def test_acl_revoked_during_provider_discards_result(fx):
    f, c = fx
    async def provider(*args, **kwargs):
        f.authorization.require.side_effect = AuthorizationError('PRIVATE_REVOKED')
        return Summary('PRIVATE_RESULT', (Topic('PRIVATE_TOPIC'),))
    f.provider.generate.side_effect = provider
    req = interaction()
    await c.execute(req, Query())
    assert not f.service._results and not c._views
    req.followup.send.assert_awaited_once()
    assert req.followup.send.call_args.kwargs['ephemeral']
    assert 'PRIVATE' not in str(req.followup.send.call_args) + repr(f.buffer.drain())

@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['refresh', 'advanced', 'detail', 'page', 'modal'])
async def test_every_component_rechecks_requester_acl(fx, action):
    f, c = fx
    await c.execute(interaction(), Query())
    result = next(iter(f.service._results.values()))
    f.provider.generate.reset_mock()
    f.authorization.require.side_effect = AuthorizationError('PRIVATE_ACL')
    req = interaction(user=301)
    if action == 'refresh': await c.refresh(req, result.id)
    elif action == 'advanced': await c.advanced(req, result.id)
    elif action == 'detail': await c.detail(req, result.id, result.id+':0')
    elif action == 'page': await c.page(req, result.id, 0)
    else: await c.submit_modal(req, result.id, 500, Query())
    f.provider.generate.assert_not_awaited()
    req.response.send_message.assert_awaited_once()
    assert req.response.send_message.call_args.kwargs == dict(content=AuthorizationError.default_safe_message, ephemeral=True)
    req.response.send_modal.assert_not_awaited()
    req.response.edit_message.assert_not_awaited()
    req.followup.send.assert_not_awaited()
    assert not c._modals

@pytest.mark.asyncio
async def test_capture_prompt_limit_newest_chronological_and_all_scopes(fx):
    f, c = fx
    scope = Scope(100,200)
    for i in range(2, 1102):
        f.capture.add(Message(scope, i, f.clock.now(), 'synthetic', str(i)+':'+'x'*3990))
    assert len(f.capture.read(scope)) == 1000
    assert f.capture.read(scope)[0].id == 102
    f.capture.add(Message(Scope(101,201), 9999, f.clock.now(), 'OTHER', 'PRIVATE_OTHER_SCOPE'))
    await f.service.submit(100,300,200,Query())
    prompt = f.provider.generate.call_args.args[0]
    rows = json.loads(prompt.data)['messages']
    assert sum(len(json.dumps(row,ensure_ascii=False)) for row in rows) <= 100000
    ids = [int(row['text'].split(':')[0]) for row in rows]
    assert ids == list(range(ids[0],1102))
    assert len(rows) < 1000 and ids[-1] == 1101
    assert all(set(row) == {'time','author','text'} for row in rows)
    assert 'PRIVATE_OTHER_SCOPE' not in prompt.data

@pytest.mark.asyncio
async def test_all_100_topics_community_access_and_stable_old_results(fx):
    f, c = fx
    f.provider.generate.return_value = Summary('overall', tuple(Topic(str(i)) for i in range(100)))
    await c.execute(interaction(), Query())
    result = next(iter(f.service._results.values()))
    seen = []
    for page in range(4):
        req = interaction(user=301)
        await c.page(req,result.id,page)
        payload = req.response.edit_message.call_args.kwargs
        assert len(payload['embed']) <= 6000
        seen.extend(option.value for option in payload['view'].children[2].options)
    assert seen == [result.id+':'+str(i) for i in range(100)]
    for token in seen:
        req = interaction(user=301)
        await c.detail(req,result.id,token)
        assert req.response.send_message.call_args.kwargs['ephemeral'] is True
        assert req.response.send_message.call_args.kwargs['embed'].title.endswith(': '+token.rsplit(':',1)[1])
    refresh = interaction(user=301,message=500)
    refresh.followup.send.return_value.id = 501
    await c.refresh(refresh,result.id)
    assert f.service.result(result.id,100,200,500) == result
    assert len(f.service._results) == 2

@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['cancel','timeout','transport'])
async def test_stream_fault_closes_http_context_and_no_retry(fault):
    entered, ended = asyncio.Event(), asyncio.Event()
    class Response:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self,*args): ended.set()
        @property
        def content(self): return self
        async def iter_chunked(self,n):
            entered.set()
            yield b'{'
            if fault == 'timeout': raise TimeoutError('PRIVATE_HTTP')
            if fault == 'transport': raise OSError('PRIVATE_HTTP')
            await asyncio.Event().wait()
    session = SimpleNamespace(post=MagicMock(return_value=Response()),close=AsyncMock())
    provider = GeminiProvider('SYNTHETIC_KEY',session=session)
    task = asyncio.create_task(provider.generate(Prompt('app','synthetic'),remaining=0.5))
    try:
        await asyncio.wait_for(entered.wait(),1)
        if fault == 'cancel': task.cancel()
        expected = {'cancel':asyncio.CancelledError,'timeout':DeadlineExceededError,'transport':ExternalTemporaryError}[fault]
        with pytest.raises(expected) as exc: await asyncio.wait_for(task,1)
        assert ended.is_set() and 'PRIVATE' not in str(exc.value)
        session.post.assert_called_once()
        timeout = session.post.call_args.kwargs['timeout']
        assert timeout.total == timeout.connect == timeout.sock_read == .5
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        await provider.close()
    session.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_one_failed_source_keeps_other_source_ready(fx):
    from discordbot.summary.adapters.runtime import SummaryResource
    from discordbot.platform.errors import ConflictError
    f, c = fx
    bot = SimpleNamespace(add_cog=AsyncMock(),remove_cog=AsyncMock(),add_listener=MagicMock(),remove_listener=MagicMock(),close=AsyncMock())
    resource = SummaryResource(bot,f.config,f.provider,f.clock,f.service.telemetry)
    async def page(scope,**kwargs):
        if scope.guild == 100: raise ExternalTemporaryError('PRIVATE_HISTORY')
        return (Message(scope,2,f.clock.now(),'synthetic','synthetic'),)
    resource.history = SimpleNamespace(page=page)
    try:
        await resource.start()
        await resource.ready()
        await asyncio.wait_for(resource._preload,1)
        assert not resource.service.capture.ready(Scope(100,200))
        assert resource.service.capture.ready(Scope(101,201))
        resource.service.authorization.require = AsyncMock()
        with pytest.raises(ConflictError): await resource.service.submit(100,300,200,Query())
        result = await resource.service.submit(101,300,201,Query())
        assert result.scope == Scope(101,201)
        assert 'PRIVATE' not in repr(f.buffer.drain())
    finally:
        await resource.stop()
    assert not resource.background.snapshot().active
    assert not resource.service.supervisor.snapshot().active
    assert not resource.service.capture.read(Scope(101,201))

@pytest.mark.asyncio
@pytest.mark.parametrize('notice_fails',[False,True])
async def test_real_resource_stop_closes_ui_capture_and_both_supervisors(fx,notice_fails):
    from discordbot.summary.adapters.runtime import SummaryResource
    f,c = fx
    bot = SimpleNamespace(add_cog=AsyncMock(),remove_cog=AsyncMock(),add_listener=MagicMock(),remove_listener=MagicMock(),close=AsyncMock())
    resource = SummaryResource(bot,f.config,f.provider,f.clock,f.service.telemetry,owns_bot=True)
    resource.service.authorization.require = AsyncMock()
    resource.history = SimpleNamespace(page=AsyncMock(return_value=()))
    source = Scope(100,200)
    resource.service.capture.add(Message(source,1,f.clock.now(),'synthetic','synthetic'))
    await resource.service.capture.preload(source,resource.history)
    provider_entered,history_entered,provider_ended,history_ended = [asyncio.Event() for _ in range(4)]
    async def blocked_provider(*args,**kwargs):
        provider_entered.set()
        try: await asyncio.Event().wait()
        finally: provider_ended.set()
    async def blocked_history(*args,**kwargs):
        history_entered.set()
        try: await asyncio.Event().wait()
        finally: history_ended.set()
    task = None
    try:
        await resource.start()
        await resource.controller.execute(interaction(),Query())
        result = next(iter(resource.service._results.values()))
        view = resource.controller._views[result.id][0]
        req = interaction()
        await resource.controller.advanced(req,result.id)
        modal = req.response.send_modal.call_args.args[0]
        f.provider.generate.side_effect = blocked_provider
        pending = interaction()
        if notice_fails: pending.followup.send.side_effect = RuntimeError('PRIVATE_NOTICE')
        task = asyncio.create_task(resource.controller.execute(pending,Query()))
        await asyncio.wait_for(provider_entered.wait(),1)
        resource.history.page.side_effect = blocked_history
        await resource.ready()
        await asyncio.wait_for(history_entered.wait(),1)
        await asyncio.wait_for(resource.stop(),1)
        with pytest.raises(asyncio.CancelledError): await asyncio.wait_for(task,1)
        await settled()
        assert provider_ended.is_set() and history_ended.is_set()
        assert view.is_finished() and modal.is_finished()
        assert not resource.controller._views and not resource.controller._modals
        assert not resource.service._results and not resource.service.capture.read(source)
        assert resource.service.active == resource.service.waiting == 0
        assert not resource.background.snapshot().active and not resource.service.supervisor.snapshot().active
        pending.followup.send.assert_awaited_once()
        assert pending.followup.send.call_args.kwargs['ephemeral']
        assert resource._closed and resource.startup_cleanup_complete
        bot.close.assert_awaited_once()
        f.provider.close.assert_awaited_once()
        assert bot.remove_listener.call_count == 3
        await resource.ready()
        assert not resource.background.snapshot().active
        assert 'PRIVATE' not in repr(f.buffer.drain())
    finally:
        if task is not None:
            if not task.done(): task.cancel()
            await asyncio.gather(task,return_exceptions=True)
        await resource.stop()
```
