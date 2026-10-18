# A2-N1 documentation inventory remediation - 2026-10-09

**Local remediation PASS; A2-N1 MINOR submitted for independent closure, not CLOSED.**
Full-source acceptance remains **PARTIAL**. No application defect or runtime change.
Branch `codex/rebuild-v2`, unchanged HEAD `cb54da9948370db64133a0ead6c9df89d0b61055`;
the dirty working tree, not HEAD alone, identifies these test/document changes.

## Contract reconstruction and bounded correction

- Original partition contract: commit `bc4d65bf4058bb87c4cf25f41883d68120839fe4`,
  rebuild README and its documentation test, separate frozen `baseline/`, living
  `current/` and historical `phases/`. This fixed inventory remains checked exactly
  as before, including bounded named current extensions.
- Commit `4902d0146f5412d8983748f9ddc350406287a996` repaired A0 document checks and
  admitted named audit additions/export exclusion, but captured the then-current
  audit directory as exactly `{a0-phase-0-report.md}`. It was a snapshot ceiling,
  not a prohibition on later authorized audit reports.
- [S0 active-state B/F](../current/final-audit-active-state.md#f-session-isolation-and-remediation)
  requires per-phase audits, evidence links and separate remediation reports;
  [ledger](../current/final-audit-ledger.md) specifies phase rows and finding/report
  links. [Index counts and precedence](../current/final-audit-document-index.md#counts-and-master-orchestration-authority)
  distinguish 24 original documents (22 frozen + D22/D23) from supplemental reports,
  and explicitly exclude handoff exports from authority. These scoped additions
  preserve the original partition; they do not waive it.
- [A2 finding](a2-phase-2-report.md) explicitly identifies A2-N1 as the stale A0-only
  ceiling, calls A1/A2 legitimate and requires bounded inventory/link checks to be
  retained. The [latest independent execution](import-probe-independent-verification-20261009.md)
  reproduces the same failure. [Phase 11 preservation plan](phase-11-inventory-plan-20261009.md)
  L09 requires retaining audit history. There is no unresolved contract conflict.

Before editing, all **67** canonical audit Markdown files were reachable from the
three current audit authorities, directly or through linked canonical audit reports.
After adding this report there are **68**; neither count is an asserted quota.
The implementation now requires the three authority files and the original A0 report,
follows their local Markdown links only within `final-audit/`, requires every routed
Markdown target to be a file, and rejects every unrooted audit Markdown file (including
nested files and disconnected cycles). A future report needs an explicit canonical
routing relationship, not a test allowlist edit. Export links cannot admit documents.
This checks documentary routing, not the semantic truth or approval of report claims.

Only [test_rebuild_documentation.py](../../../tests/architecture/test_rebuild_documentation.py)
changes test logic. Root/baseline/current/phase assertions remain. The existing
relative-link/heading-anchor validator is extracted with a root parameter for synthetic
negative cases; its assertion policy and export exclusion remain, with diagnostics
relative to the supplied rebuild root. No filename regex, skip or arbitrary-file waiver.
Three routing notices are additive; no historical evidence or ledger phase verdict changes.
Root AGENTS.md applies; no nested AGENTS or local `.agents/skills`/`.codex/skills` exists.
No artifact-generation/other available skill is needed for this repository test repair.

## Exact focused executions and evidence

All commands ran at repository root in the **default permitted sandbox** using the
unchanged guarded runner. No outside-sandbox run or broad collection/suite was requested.
`--confcutdir=tests/architecture` excludes the application/DB fixture; the runner still
installs the root credential boundary and operational-data/network guard. These tests
read documentation or synthetic temporary Markdown only. Plugin autoload was disabled.

```powershell
.\.venv\Scripts\python.exe -I -B scratch/a2-n1-20261009-01/evidence.py entry
.\.venv\Scripts\python.exe -I -B scratch/a2-n1-20261009-01/topology.py
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -I -B docs/rebuild/final-audit/a8r4-test-runner.py -q --tb=short -p no:cacheprovider --confcutdir=tests/architecture -o asyncio_mode=strict tests/architecture/test_rebuild_documentation.py --junitxml=scratch/a2-n1-20261009-01/red.xml
.\.venv\Scripts\python.exe -I -B docs/rebuild/final-audit/a8r4-test-runner.py -q --tb=short -p no:cacheprovider -p pytest_asyncio.plugin --confcutdir=tests/architecture tests/architecture/test_rebuild_documentation.py --junitxml=scratch/a2-n1-20261009-01/green.xml
.\.venv\Scripts\python.exe -I -B docs/rebuild/final-audit/a8r4-test-runner.py -q --tb=short -p no:cacheprovider -p pytest_asyncio.plugin --confcutdir=tests/architecture --basetemp=scratch/a2-n1-20261009-01/pytest-green-02 tests/architecture/test_rebuild_documentation.py --junitxml=scratch/a2-n1-20261009-01/green-02.xml
```

| Execution | Actual result |
| --- | --- |
| Original RED, `red.xml` | 2 PASS / 1 FAIL, 3.29s; original line 92. One unknown asyncio_mode config warning because plugin was not loaded. |
| First post-edit attempt, `green.xml`/`green.txt` | 3 PASS / 11 setup ERROR, 5.84s; sandbox-default pytest numbered temporary directory could not be created. No negative case executed. Retained, not labeled GREEN. |
| Same sandbox, explicitly fresh workspace basetemp, `green-02.xml`/`.txt` | **14 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, 5.44s; plugin explicitly loaded, no warnings. |

The 14 include the original three cases, one positive routed-growth/cycle case, and
**10 negative cases**: three missing authorities, missing A0 even after all references
are removed, a missing index-routed successor, two unrooted files (top/nested, including
misleading export links), a disconnected cycle, a missing link target and a bad anchor.
Temporary trees are owned synthetic fixtures; no existing directory was removed to retry.

| SHA-256 identity | Value |
| --- | --- |
| Original test bytes | `d6b62d54285e06cca4dc6de21f20751364b746440d02771dbffa5a3a43c092e3` |
| Corrected test bytes before final comment clarification | `786c8a4dea2320ba880ecbc25e9a7816df30fffe2f023358153aba53dcc48e05` |
| Final corrected test bytes | `b2a46cd61685f209fc09de8ec57e3641f617d315112519f14d4562c45a34ded5` |
| RED JUnit | `d3be8c0e9567cf248fd608b890d56a55f3545d688fd20d53ff6cdfb7ede54329` |
| Setup-error JUnit | `e6643883ab68dbfe0e22e00ae9feaddc891e192640657ab58d07e088c03cfa20` |
| GREEN JUnit | `aa74061d596d7d5a9d11ecb181639eaa0b5ccd4bf5745e8a76dceb9a3cdc4efa` |

## Preservation, disposition and next gate

[Local receipt directory](../../../scratch/a2-n1-20261009-01/) retains entry hashes,
four exact pre-edit copies, all execution receipts, task-only patch and final file hashes.
The entry covers **938 safe source/document/evidence files**, including prior import and
admission scratch evidence. Final comparison permits only the test and three routing
documents to differ, plus this new report; **934 inherited hashes remain equal**.
HEAD, branch, refs and raw Git index remain equal; staging remains empty. No fetch.
The routing insertions preserve every pre-existing byte. No archive roots, runtime,
guards/runners, installed selection or prior receipts were edited. Excluded operational
and credential content was never opened; the manifest is not an all-files secret scan.

After report/routing authoring the same focused selection again passed **14/14**
in **5.44s**, including repository-wide rebuild link/anchor checks, with a new
`--basetemp=scratch/a2-n1-20261009-01/pytest-final` and
`--junitxml=scratch/a2-n1-20261009-01/final-tests.xml`; console is `final-tests.txt`.
A final comment clarifies that the current audit authorities are now required;
`pytest-final-current` / `final-current.xml` / `final-current.txt` retain the same
focused command against the final exact test bytes (all other options unchanged).
`evidence.py final`, `git diff --check`, `git diff --cached --check`, and task-only patch
review establish the exact final scope. Rollback is only this test patch, three inserted
notices and new report; do not reset inherited dirty files or delete historical evidence.

No Pi, network, real DB, credential, package, permission, cleanup, commit/push or deployment
operation occurred. Prior independent installed588/source127 PASS is retained in its
scope. The consumed single full-source run remains 1885 collected, 13 PASS / 1 FAIL /
1871 NOT_RUN in 5.188s outer; these local results do not rewrite it. Historical Deno,
dependency, Linux/systemd and unsupported-child limits remain unverified here. A9/A10
BLOCKED, Integrated administrative SCOPE-CLOSED, 23 operational obligations and deferred
Phase 11 remain unchanged. Current suite membership is not freshly collected; this file
adds 11 cases to the original three.

**One next step: independent review of this exact patch, authority derivation and negative
coverage for A2-N1 closure and full-suite readiness.** A later authorized full-suite plan
should collect all failures where safe instead of repeatedly stopping at known non-material
findings. Runner behavior is unchanged here; no new execution authorization is implied.
