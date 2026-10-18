# A6 - Independent Phase 6 Watch Together audit

2026-10-02. **PHASE 6 FAIL. A6-M1 MATERIAL OPEN.**
Stop for parent review and separately authorized remediation. No product/test fix,
weakened assertion, A7 or Integrated Audit was performed.

## Scope and authority

Entry/evidence HEAD `97f332225c204de02ae6933e4526b7c2f113987c`, branch
`codex/rebuild-v2`. Active-state, ledger and document index were read first.
Principal governing sources reviewed: B20 Phase 6 exit; B03 F037-F043;
B12 FR-038-044 with FR-004/005/006/008/009; scoped B11/B13-B19/B21;
C1 Watch compatibility and C2 CF-10/11/12/13/16/19/20;
[Watch contract C8](../phases/phase-06/watch-contract.md),
[loopback contract C9](../phases/phase-06/loopback-contract.md),
D23 ADR-004/005/012/021 and scoped D22/product-spec.
[Original Phase 6 report](../phases/phase-06/phase-6-report.md) remains historical.
Repository AGENTS applies; no audit-specific local skill or applicable artifact/app
skill was found. No sub-agent was used.

Reviewed current session/service/controller, public HTTP/WS/ingress, authenticated
control, capability/policy, SQLite writer, Discord adapter, web resource/production
composition, shipped browser script and focused assertions/fixtures. Compare original
Phase 6 commits `4c31a83`, `cf222bf`, `93b6d0a`, report `a2f4686`; later hydration
`b03b785`, authority reconciliation `63a3ec6`, iframe initialization `e327bea`, and
nested lifecycle ownership changes exercised in current tests. These later paths were
not inferred correct from their historical completion claims.

Explicit supersessions: P2 Gates23/26 allow one ordinary play action after single-browser
refresh; autoplay is optional, while paused state/video/position and other-client
non-interruption remain required. Gate27 supersedes the older multi-client-unresolved
wording. Later server-owned hydration intentionally replaces peer-solicited snapshots;
C8/C1's old join/sync_request wording describes the original behavior. This audit does
not classify that accepted later change as a defect. P2 Gate29 and the D7 receipt
explicitly require/claim terminal target playback/audio stop with unrelated C intact.
The finding below concerns termination, not the accepted refresh exception.

## A6-M1 - Terminal browser keeps playing after administrator close

**MATERIAL, OPEN.** Affected F042 / FR-043, C8 terminal closure and subsequent P2
Gate29 acceptance. Server revocation alone does not implement the browser media outcome
recorded in the later close gate.

Exact current path:

- `watch/application/session.py:139-147`: terminal close clears peers, stops each pump
  with authoritative code4001 and durably closes the session.
- `watch/adapters/templates/player.html:1241-1250`: active socket terminal callback
  sets `terminal`, clears reconnect timer and changes badge/toast, then returns.
  It issues no media pause/stop/destroy/unload operation.
- `player.html:1281-1283` routes best-effort session_closed to socket.close(4001),
  hence the same omission. The remaining player/interval paths guard on terminal;
  they do not stop the independently running iframe.
- Existing `playback_browser_harness.cjs:168-170` terminal tests never ready/start the
  iframe and assert only socket count. Their PASS cannot establish stopped playback.

Independent exact shipped-script probe starts target T and unrelated control C playing
synthetic video `aaaaaaaaaaa` at42s, delivers the server's terminal4001 to T, triggers
online/pageshow, then advances both clocks2s. It verifies terminal=true, one target
socket/no reconnect and unaffected control before asserting target media stopped.
Actual: **T remains PLAYING(1), time44; C remains PLAYING(1), time44**.
Target has only its original playing load command. The final media assertion FAILS.
No production media, YouTube fetch or real user content participates.

```json
{"terminal":true,"targetState":1,"targetTime":44,"targetSockets":1,"targetCommands":["playing"],"controlState":1,"controlTime":44}
```

Companion server probe PASS traverses current Discord controller -> signed in-process
HTTP -> Watch actor/temp SQLite -> fake socket. Master close delivers4001, removes
T/peers/known messages and acknowledges cleanup; another guild's room and peer survive.
Thus the reproduced missing action is in the shipped browser terminal callback, not a
claim that server session revocation or message deletion failed.

`git diff 8e9018d4b8061cde6006eee47fa4103522f77718 --` for player.html and session.py
is empty. This is not a new uncommitted template regression. D7's human-confirmed
playback/audio-stopped observation is preserved verbatim in its receipt, but it cannot
prove a terminal-stop code path that is absent. The cause of that historical human
observation is unknown; this audit does not reinterpret it as measured live failure.

## Fresh evidence and limits

Existing Windows `.venv`, Python3.12; Node24.16.0. No install/upgrade.
PYTHON_DOTENV_DISABLED=1; strict RuntimeWarning/PytestUnraisableExceptionWarning.
Existing fixtures and the completed independent invocation enforce root credential
boundary; every DB/backup is temporary synthetic, Discord/metadata are mocked,
control/public HTTP and WS tests are in-process ASGI. Node uses controlled DOM/iframe/
WebSocket VMs with no network. No listener was opened; localhost3000/MyFood was untouched.

| Completed distinct selection | PASS | FAIL | SKIP / XFAIL |
| --- | ---: | ---: | ---: |
| Watch integration plus Watch characterization | 132 | 0 | 0 / 0 |
| Independent exact appendix, server + active-media close | 1 | 1 | 0 / 0 |
| **Disjoint total** | **133** | **1** | **0 / 0** |

First selection completed in9.95s, second in0.80s. Both emit the known audioop warning.
Direct Node reproduction also exits1 with A6-M1; it is the same failing scenario and
is not counted as another unique test. Three preliminary TEMP pytest launches omitted
explicit `-c pyproject.toml`, printed .F and failed to finish promptly; only those owned
processes were interrupted. Root cause of that launcher/reporting stall was not established.
They are incomplete runs, not extra test receipts. The final explicit-config run
completed normally without changing probe assertions, product code or repository tests.

```powershell
.venv/Scripts/python.exe -m pytest tests/integration/watch/ tests/characterization/test_watch_contracts.py -q -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

For the appendix save its exact Python to a new TEMP directory. From repo root run:

```python
import sys, runpy
from pathlib import Path
runpy.run_path(str(Path.cwd() / 'conftest.py'))
sys.path[:0] = [str(Path.cwd() / 'src'), str(Path.cwd() / 'tests')]
import pytest
probe_dir = Path(TEMP_PROBE_DIRECTORY)
raise SystemExit(pytest.main([
    str(probe_dir / 'test_a6_terminal.py'), '-c', 'pyproject.toml', '-q', '-s',
    '--tb=no', '--confcutdir=' + str(probe_dir),
    '-W', 'error::RuntimeWarning', '-W', 'error::pytest.PytestUnraisableExceptionWarning',
]))
```

Scoped existing assertions freshly cover durable invite/compensation/single response,
master denial/close, HMAC replay/origin/CSRF/input caps, HTTP routes/ASGI WS, session/guild
isolation, peer pressure/rates, 30+5s and reconnect/absolute expiry, stale-owner/readiness,
close/add races, cancellation/cleanup, old readers/encrypted temporary backup and current
browser reconciliation. These are supporting evidence, **not an all-gates PASS**.
On the material finding, further audit expansion stopped per assignment. No extra browser
UI, actual loopback TCP, genuine process/Linux, Pi capacity/soak, proxy/Cloudflare or
live Discord permission test was performed. No whole-suite clean claim; known inventory
and Deno failures, audioop, A3-N1 MINOR and A3-I1 INFO remain unchanged.

## Ownership, commit and next boundary

[Entry inventory](a6-entry-inventory.json) lists all70 inherited hashes/statuses:
11 modified /59 untracked, empty index. All70 matched before owned authority edits;
no runtime/test/config drift occurred. Inherited modified files: CHANGELOG, README,
product-spec, rebuild README, current-plan, active-state, ledger, A3 report, full-sweep
report, Phase10 report and browser/watch_fixture.py. Inherited untracked groups:
mixed document index, Phase10B active-state/ledger/receipts, A0-A2 reports, handoff
export/zip, invite guide and two browser scripts. Full individual paths are in inventory.

Owned only: report/embedded exact probe, inventory, active-state AP append, Phase6 ledger
row and index A6 navigation append. Commit new report/inventory and only AP/Phase6
changes against HEAD, preserving mixed prior authority/index work uncommitted. Review
staged diff and `git diff --cached --check`; local commit only, no push. Expected residual
11 modified/59 untracked, empty index after commit. Preservation is checked by removing
only the owned append/row changes in memory and comparing all70 original hashes.
Final commit identity is supplied in handoff. Rollback is a documentation-only revert
of this owned commit; do not reset mixed work or discard historical evidence.

Production not accessed or changed. Recorded source
`8e9018d4b8061cde6006eee47fa4103522f77718`, pin
`r-8e9018d4b8061cde-3dac82a792fad576` remain separate. No public endpoint, real playlist,
Discord send, credential/permission, real DB/restore, deployment/restart, systemd,
Cloudflare, V1, concurrent writer or release-history cleanup action. A0-A5 remain PASS.
Integrated Audit deployment condition unmet; friend activation HELD; MyFood paused.

**STOP A6. NEXT: parent review of A6-M1, then separately authorized narrow terminal-media
remediation and independent Phase6 re-verification.** No remediation design is implemented;
no A7, Integrated Audit, Phase11 or production action is started.

## Exact synthetic reproducer

The Node prefix is read unchanged from the current repository harness; the extra scenario
runs the actual shipped inline JavaScript. The test lives only in TEMP, not tests/.

```python
import asyncio
import json
from pathlib import Path
import subprocess
import pytest
from characterization.watch_support import harness, interaction
from discordbot.watch.adapters.discord_io import DiscordInteraction
from tests.integration.watch.conftest import Socket

ROOT = Path(r"C:\Users\dlrjs\Desktop\1_programming\4_python\discord_bots\DiscordBot")

@pytest.mark.asyncio
async def test_admin_close_server_cleanup_and_other_guild_isolation(tmp_path):
    async with harness(tmp_path) as h:
        await h.controller.request(DiscordInteraction(interaction(h.clock), 'https://watch.example.test'))
        target = next(iter(h.service.sessions.values()))
        token, _ = h.service.capability.mint(100, 42, '1001', int(h.clock.now().timestamp()))
        sock = Socket()
        _, peer = await h.service.connect(token, sock)
        await h.service.add(token, 'https://youtu.be/aaaaaaaaaaa', 'Synthetic')
        other = await h.service.create(200, 43, 'a6-control', int(h.clock.now().timestamp()))
        control_socket = Socket()
        control, control_peer = await h.service.connect(other.capability, control_socket)
        await h.controller.master_close(42, target.intent.session_id)
        await asyncio.wait_for(peer.task, 1)
        assert sock.codes == [4001]
        assert target.closed and not target.peers
        assert target.intent.session_id not in h.service.sessions
        assert (await h.client.call('cleanup', {})) == {'items': []}
        assert h.channel.get_partial_message.return_value.delete.await_count == 2
        assert h.service.resolve(other.capability) is control and not control.closed
        assert not control_peer.failed and not control_socket.codes


def test_terminal_close_stops_active_iframe_without_affecting_other_room(tmp_path):
    harness_source = (ROOT/'tests/integration/watch/playback_browser_harness.cjs').read_text(encoding='utf-8')
    prefix = harness_source.split('const scenario=process.argv[3];')[0]
    probe = r"""
const targetRoom = new Room(current()), controlRoom = new Room(current());
const target = client(targetRoom), control = client(controlRoom);
for (const c of [target, control]) {c.ready(); c.open(); c.frame.complete();}
assert.equal(target.frame.state, 1);
assert.equal(control.frame.state, 1);
target.sockets[0].close(4001);
target.listeners.get('online')(); target.listeners.get('pageshow')();
target.tick(2000); control.tick(2000);
assert.equal(vm.runInContext('terminal', target.ctx), true);
assert.equal(target.sockets.length, 1);
assert.equal(control.frame.state, 1);
console.log(JSON.stringify({terminal: vm.runInContext('terminal', target.ctx),
    targetState: target.frame.state, targetTime: target.frame.getCurrentTime(),
    targetSockets: target.sockets.length, targetCommands: target.frame.commands,
    controlState: control.frame.state, controlTime: control.frame.getCurrentTime()}));
assert.notEqual(target.frame.state, 1, 'A6-M1: terminal 4001 must stop target media');
"""
    runner = tmp_path/'a6-terminal.cjs'
    runner.write_text(prefix + probe, encoding='utf-8')
    result = subprocess.run(['node', str(runner), str(ROOT/'src/discordbot/watch/adapters/templates/player.html')],
        capture_output=True, text=True, encoding='utf-8', timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
```
