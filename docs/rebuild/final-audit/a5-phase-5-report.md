# Final Audit A5 - Phase 5 Summary

Date: 2026-10-02. **FAIL - A5-M1 MATERIAL OPEN. STOP for parent review.**
Audited branch `codex/rebuild-v2`, entry HEAD `816c258df5c4e17414fa0f0e2e9ab5dfd40794ef`.
This is one independent audit, with no product remediation and no A6 work.

## Scope and authority

F006-F010 / FR-026-030: configured guild/source message capture, bounded retention and
reconciliation; basic/advanced/refresh/topic Summary; source access and privacy;
Gemini request limits, failure/cancellation/deadline handling and Discord response lifetime.

Read current final-audit active-state, ledger and document index first. Latest entry
routing is active-state AL: A0-A4 PASS, A5 previously NOT_AUDITED. User assignment
advances exactly A5; earlier historical continuation text does not authorize other work.

Governing sources:
- [C7 Summary contract](../phases/phase-05/summary-contract.md), particularly ACL/privacy,
  concurrency/deadline and failure/shutdown; [B20 Phase 5 exit](../baseline/20-migration-plan.md).
- [C1 Summary characterization](../phases/phase-01/characterization-contracts.md),
  [C2 CF-08/09/16/19/20](../phases/phase-01/concurrency-failure-plan.md),
  [B12 FR-026-030](../baseline/12-functional-requirements.md).
- [D23 ADR-020](../current/architecture-decision-log.md),
  [D22 Q-H01/03/04/11, Q-M04/07, Q-L02](../current/open-questions.md): preserve public
  results/private details and three-field modal; source ACL, minimum external data,
  per-guild configuration, pagination and KST. C7 explicitly resolves historical date
  picker/refresh-in-place descriptions to actual preserved UI behavior.
- B13 NFR-003/013/014/035, B15 ownership/deadline, B16 response/error boundary,
  B18 Summary privacy, B19 synthetic failure tests; C3 platform cancellation and later
  nested-cleanup ownership overlays. S1 Summary intent and T Phase 5 trace were consulted.
- [Historical Phase 5 report](../phases/phase-05/phase-5-report.md), including its
  synthetic-only results and live evidence limits. AGENTS.md read. No subordinate
  AGENTS.md or repository-local SKILL.md was found in the scoped locations; available
  artifact/image/app skills do not apply to this repository code audit.

Current code inspected: `src/discordbot/summary/{domain,application,adapters}`
contracts and implementation paths, `composition/summary.py`, and Summary production
wiring in `composition/production_discord.py`. Tests reviewed before execution include
root credential/temporary-DB fixtures, synthetic harness, Summary integration and the
selected characterization cases. No real history, credential, database or provider used.

## Finding A5-M1 - native cancellation lost when its UI notification fails

**MATERIAL; open; separate remediation required.** C7 Failure and shutdown explicitly
requires native asyncio cancellation to propagate while notifying privately at most once
when possible. This is a required control-flow invariant, not an optional UI cosmetic.

`src/discordbot/summary/adapters/discord_ui.py:109-115`: the CancelledError handler awaits
`responder.error(...)` before its bare `raise`. If the Discord followup fails,
`Responder._call` (23-32) wraps it as `ResponderFailure`. The outer handler catches that
new exception, emits `summary.response/delivery_failed` and returns normally; the
original cancellation never reaches the caller.

Exact synthetic trigger: defer a Summary request, block its mock provider on an Event,
cancel the controller task, and make the single private cancellation followup raise
`RuntimeError('SYNTHETIC_DELIVERY_FAILURE')`.

| Observation | Successful notification control | Failed notification reproducer |
| --- | --- | --- |
| `CancelledError` reaches caller | true | **false** |
| `task.cancelled()` | true | **false** |
| `task.cancelling()` / `task.done()` | 1 / true | 1 / true |
| Provider cancelled, reservations/results/views released | yes | yes |
| Private notification attempts | 1 | 1 |

The cancelled request becomes normal completion to its caller. This breaks cancellation
ownership at the common controller boundary used by Summary commands/components/modal
submissions. The demonstrated case does **not** show data disclosure, duplicate sends,
unbounded work or orphaned provider tasks; do not inflate it into those claims.

Existing tests cover cancellation with successful followup and uncertain delivery with
ordinary provider errors separately. They miss cancellation plus notification failure.
The probe asserts existing cleanup, privacy and single-send invariants before the failing
native-cancellation assertion; no assertion was weakened and no product test was changed.

Git blame attributes the handler to `643b75a6` (original Phase 5 adapter commit). The
current UI file SHA-256 is `4cc4103f66fb7eba7416636f28dd38f53ec618d8e544a89adb21c52ccd7eede5`.
This is an original uncovered Phase 5 defect, not evidence of a new A2/A4 regression.
Later `868cea73f9087fc12aec077ec9211916b6343cc8` added allowlisted provider diagnostics;
`d042e5e537c52bd25dbc1d437b575a1178b991f7` tightened nested cleanup ownership. Neither
changes or waives this cancellation requirement. A0-A4 verdicts are not invalidated.

## Fresh executed evidence and limits

Existing Windows Python 3.12 `.venv`; `PYTHON_DOTENV_DISABLED=1` and
`PYTHONIOENCODING=utf-8`. All external dependencies are synthetic mocks/fakes.

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/summary/ tests/characterization/test_summary_contracts.py tests/characterization/test_component_contracts.py::test_f009_f010_fr028_fr029_preserve_summary_components tests/characterization/test_component_contracts.py::test_f010_fr029_correct_summary_topics_paginate_with_stable_ids -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

**85 PASS / 0 FAIL / 0 SKIP / 0 XFAIL, 1.47s**; one inherited `audioop` deprecation.
An earlier launch of the same selection yielded before its result was captured; only
this completed receipt is counted, once. No successful result is inferred for that launch.

Save the exact appendix as `$env:TEMP\discordbot-a5-cancellation-probe.py`, then from
repository root:

```powershell
.venv\Scripts\python.exe -m pytest "$env:TEMP\discordbot-a5-cancellation-probe.py" -c pyproject.toml --confcutdir $env:TEMP -q -s -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

**1 PASS / 1 FAIL / 0 SKIP / 0 XFAIL, 0.93s**, exit 1. The failed parameter is `[True]`;
assertion: `assert propagated and task.cancelled()`. Probe explicitly installs the root
credential guard, uses only synthetic messages and mock provider/Discord I/O, and
cancels/awaits its task, closes controller views and stops its service in `finally`.
The two disjoint selections give **86 PASS / 1 FAIL / 0 SKIP**. No full suite or broad
architecture sweep was run after the material finding; stop policy takes precedence.

| Phase gate | Evidence obtained before STOP |
| --- | --- |
| Capture/retention/reconnect/isolation | Current implementation review; existing synthetic capture/lifecycle tests pass |
| Source ACL and minimal prompt/telemetry data | Current adapter/service review and existing fake tests pass; actual channel/member cache deployment is not newly verified |
| Basic/advanced/refresh/topic UI and bounds | Selected golden/V2 cases pass, including topic 26 and maximal embed; live UI unverified |
| FIFO/limits/deadline/provider errors | Existing synthetic request/Gemini/failure tests pass; no live HTTP/model guarantee |
| Cancellation/response lifecycle | **FAIL A5-M1** despite ordinary paths passing |
| Whole-phase completion | **FAIL, early material stop**; no exhaustive PASS for unchallenged interleavings or whole architecture |

Historical Phase 5 counts (434 PASS/4 XFAIL and repeated concurrency selections) remain
historical receipts, not current proof. Current execution corroborates the tested paths
but narrows the historical broad cancellation claim. No old evidence was rewritten.
P2 Phase 10B gate 6 records human `/요약` success plus request1 success telemetry for its
release; it does not establish this combined failure branch or current candidate safety.
Later production composition explicitly wires Summary with main-channel mappings and
Gemini configuration; original Phase 5 opt-in wording is historical, not a live claim.

No new minor finding assigned. Known inventory/Deno failures, inherited audioop warning,
A3-N1 MINOR and A3-I1 INFO remain disclosed and are not escalated by this audit. Live
Gateway/HTTP/Pi, actual source/result-channel permission alignment, member cache/intents,
Gemini quality/availability and Pi capacity/soak remain outside fresh verification.
No clean full-suite claim. Audit stopped at first material finding; this is not proof
that all other combined faults are absent.

## Ownership, production and next boundary

Entry inventory: [70 inherited paths/hashes](a5-entry-inventory.json), 11 modified /
59 untracked files and empty index. Before audit-record edits all 70 contents still
matched. Owned changes only: this report, entry inventory, active-state AM append,
Phase 5 ledger row, and document-index A5 navigation append. Runtime, tests, schema,
dependencies, historical reports and other user files are unchanged.

Local commit scope: new report/inventory and **only** AM/Phase 5 row changes staged
against HEAD. The pre-existing mixed active-state/ledger content and untracked document
index stay uncommitted. Preservation is checked by reversing only the three owned
authority deltas and comparing all entry hashes. After commit, residual ownership stays
11 modified / 59 untracked with empty index; final response identifies the commit SHA.
No remote push. Audit rollback is reverting only that audit commit; remove only the A5
navigation append if separately requested, preserving inherited content. No data restore.

Production untouched: recorded source `8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576`, distinct from candidate; no fresh host observation.
No production access, deployment/restart, production DB writes, credentials, external AI
calls, permission changes, systemd/Cloudflare, V1, cleanup, install or WSL activity.
Friend activation remains HELD; all final audits plus Integrated Audit deployment
condition is unmet. My Food remains paused.

**STOP A5. Next: parent reviews A5-M1 and authorizes a separate A5 remediation microphase,
then a fresh independent A5 verification.** Preserve native cancellation on notification
failure without duplicate delivery or raw diagnostic exposure; no implementation is
performed or authorized by this report. A6, Integrated Audit and Phase 11 not started.

## Exact synthetic reproducer

```python
"""A5 synthetic audit reproducer; no production data or network."""
import asyncio
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path.cwd()
runpy.run_path(str(ROOT / 'conftest.py'))  # repository credential guard
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]

from characterization.summary_support import harness, interaction, settled
from discordbot.summary.adapters.discord_ui import SummaryController
from discordbot.summary.domain.models import Query


@pytest.mark.asyncio
@pytest.mark.parametrize('notification_fails', [False, True])
async def test_native_cancel_survives_best_effort_notification(notification_fails):
    fixture = harness()
    controller = SummaryController(fixture.service)
    request = interaction()
    entered = asyncio.Event()
    provider_cancelled = asyncio.Event()

    async def provider(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            provider_cancelled.set()

    fixture.provider.generate.side_effect = provider
    if notification_fails:
        request.followup.send.side_effect = RuntimeError('SYNTHETIC_DELIVERY_FAILURE')
    task = asyncio.create_task(controller.execute(request, Query()))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        propagated = False
        try:
            await asyncio.wait_for(task, 1)
        except asyncio.CancelledError:
            propagated = True
        await settled()
        assert provider_cancelled.is_set()
        assert not fixture.supervisor.snapshot().active
        assert fixture.service.active == fixture.service.waiting == 0
        assert not fixture.service._results and not controller._views
        request.followup.send.assert_awaited_once()
        assert request.followup.send.call_args.kwargs['ephemeral'] is True
        assert 'SYNTHETIC_DELIVERY_FAILURE' not in repr(fixture.buffer.drain())
        observed = {'notification_fails': notification_fails,
                    'propagated': propagated, 'cancelled': task.cancelled(),
                    'cancelling': task.cancelling(), 'done': task.done()}
        print(observed)
        assert propagated and task.cancelled(), observed
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        controller.close()
        await fixture.service.stop()
```
