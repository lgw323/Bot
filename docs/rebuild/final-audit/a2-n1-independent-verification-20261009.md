# A2-N1 independent inventory verification - 2026-10-09

**PASS: A2-N1 MINOR independently CLOSED.** No material flaw or required remedy
found in this bounded correction. Full-source acceptance remains **PARTIAL**, not
re-executed here. Phase 2's existing scoped PASS is unchanged.

Reviewed dirty tree: branch `codex/rebuild-v2`, HEAD
`cb54da9948370db64133a0ead6c9df89d0b61055`. HEAD alone is not this candidate's identity.

## Contract and assertion review

- Read root AGENTS.md; no nested instructions under the reviewed docs/tests trees.
  Personal Context skill explicitly excludes current-source-only tasks; no remote
  retrieval or artifact skill was needed. An initial instruction-file enumeration
  encountered inaccessible unrelated scratch directories; no contents were read,
  retry/escalation attempted, or permission changed.
- Local `git show` of `bc4d65bf4058bb87c4cf25f41883d68120839fe4` README/test confirms
  frozen baseline, living current and historical phase partitions. Later phase
  deliverables extend that structure; this patch preserves all present named sets.
  `4902d0146f5412d8983748f9ddc350406287a996` admits named current extensions and
  excludes handoff exports, while adding the then-A0-only audit assertion.
- [S0 B/F](../current/final-audit-active-state.md#b-audit-purpose-and-authority-routing),
  [ledger workflow](../current/final-audit-ledger.md), and
  [index counts/precedence](../current/final-audit-document-index.md#counts-and-master-orchestration-authority)
  require subsequent audits/remediations and their evidence routing. They separate
  the 24 original authorities from supplemental reports; neither later completion
  nor copied exports can supersede governing contracts by themselves.
- [Original A2-N1, section 7](a2-phase-2-report.md) calls A1/A2 legitimate and
  requests a bounded canonical inventory while retaining partition/link checks.
  [Phase 11 L04/L09](phase-11-inventory-plan-20261009.md) requires retaining tests
  and audit history. Deleting reports or merely dropping the failing test would
  violate that contract. Required authority roots plus canonical audit reachability
  are a faithful structural correction; no permanent A0-only quota remains justified.
- All three authority files and A0 are required. Every routed audit Markdown target
  must be a file; unrooted top-level/nested documents and disconnected cycles fail.
  Traversal only proceeds through audit Markdown after the authority roots. Export
  or other-tree links cannot admit an orphan. Root/baseline/current/phase assertions
  remain intact. AST comparison confirms identical named sets, link/heading regexes,
  and link-check body after normalizing only the root parameter/diagnostic location.

The incidental-link concern was tested explicitly: a link in an export or unrelated
phase tree does **not** admit a report; an incidental link in a reachable canonical
audit report **does**. This validator proves routing, not semantic relevance or owner
approval. It cannot distinguish an example from an endorsement, or detect jointly
removing a non-A0 report and all incoming references. The original test was likewise
a current inventory check, not immutable content/history proof; L09 preservation
still requires review and receipts. No governing clause mandates a special link label,
direct listing in all three roots, or a reviewer-owned filename allowlist. Inventing
one would exceed A2-N1. This boundary does not waive preservation or validate arbitrary
new report claims. Existing parser limits (including skipped same-document anchors)
are inherited, not newly introduced or credited as repaired.

## Exact identities and fresh evidence

[Author report](a2-n1-inventory-remediation-20261009.md) and retained receipt hashes
were independently recomputed before any review documentation edits:

| Item | SHA-256 / result |
| --- | --- |
| Corrected test | `b2a46cd61685f209fc09de8ec57e3641f617d315112519f14d4562c45a34ded5` |
| Author task-only patch | `8226cc6d1766c8e9d288ba306d0e9609c6b2d8dfe51840ebdcf768ce9cfe907b` |
| Original test | `d6b62d54285e06cca4dc6de21f20751364b746440d02771dbffa5a3a43c092e3` |
| Author final snapshot | All 939 safe file hashes match; original 934-other-file preservation recomputed |
| Author artifacts | Every artifact recorded by final.json matches; three routing additions preserve earlier bytes |

All fresh executions used the default sandbox, existing `.venv`, and unchanged
canonical A8R4 credential/data/network guards. Application fixtures are excluded by
confcutdir; only documentation and new synthetic trees are exercised. Plugin autoload
and cache are disabled, asyncio plugin loaded explicitly, `-I -B` retained. The new
review wrapper bounds each test child at 300 seconds and saves command/transcript/XML/
process receipts; no timeout occurred. Mutation checks only replace helpers in memory.
The author's negative tests remove only their newly created synthetic fixture files;
no inherited file or evidence was deleted.

```powershell
.\.venv\Scripts\python.exe -I -B scratch/a2-n1-independent-20261009-01/receipt.py entry
.\.venv\Scripts\python.exe -I -B scratch/a2-n1-independent-20261009-01/run_review.py focused
.\.venv\Scripts\python.exe -I -B scratch/a2-n1-independent-20261009-01/run_review.py independent
```

The exact underlying pytest command is captured in each `*-process.json`: canonical
`docs/rebuild/final-audit/a8r4-test-runner.py -q --tb=short -p no:cacheprovider
-p pytest_asyncio.plugin`, scoped confcutdir, fresh workspace basetemp and JUnit path.

| Fresh execution | Result |
| --- | --- |
| Unchanged candidate documentation tests | 14 PASS / 0 FAIL / 0 ERROR / 0 SKIP; 5.38s console, 6.937s outer |
| Independent reviewer probes | 22 PASS / 0 FAIL / 0 ERROR / 0 SKIP; 3.45s console, 5.000s outer |
| Reviewer probe breakdown | 10 actual negative tests kill disabled-checker mutants; 8 missing/extra fixed-partition violations rejected; 3 incidental-link boundary cases; 1 AST obligation equivalence check |

These are 36 distinct local test cases, not 36 application behaviors. The ten
mutation probes expect the author's negative tests to fail with `DID NOT RAISE`
when their checker is disabled; they would fail if those tests became inert.
The ordinary 14-case run separately proves the real checker rejects all ten cases.
Post-authoring focused rerun and final preservation receipt are recorded below.

## One next step: bounded full-source evidence preparation

A2-N1 is ready for closure; full-suite execution requires a small **separate** runner
preparation/review. The existing `scratch/import-probe-20261009-01/source_checks.py`
adds `--maxfail=1` both in the source-full branch and again at the common tail, and
the original source-full receipt names already exist. A CLI suffix to its current
two-argument outer wrapper cannot override those flags safely.

Prepare a fresh `scratch/a2-n1-full-20261009-01/` copy of `run_bounded.py` and
`source_checks.py`, preserving the originals. Admit one `source-full-all` mode that
selects `tests/` and has effective `--maxfail=0` at both locations (or removes both
fail-fast flags for that mode). Retain all other guards, strict warning/xfail policy,
fresh temp ownership, exact child allowlists, 30/60-second diagnostics, 15-second
import timeout, and 300-second outer timeout/kill/reap behavior. Review the exact
new bytes before this proposed single command; **not implemented or executed here**:

```powershell
.\.venv\Scripts\python.exe -I -B scratch/a2-n1-full-20261009-01/run_bounded.py source_checks.py source-full-all
```

Run from the repository root. Default-sandbox socketpair restrictions remain known;
any outside-default-sandbox run requires exact fresh owner approval. Do not reuse the
consumed approval or silently broaden the child allowlist. Guard-denied unsupported
SQLite/TTS/staging/Node children remain visible failures for classification; continue
ordinary assertion failures within the same bounded run, stopping on timeout or any
actual containment concern. Do not add skips/xfails or retries to manufacture green.
Read child exit/result/JUnit/process receipts together: the inherited outer wrapper
can itself return zero after child failure/timeout. Timeout leaves unfinished cases
NOT_RUN. Neither wrapper is a hard whole-process-tree isolation guarantee.

The historical full-source receipt remains 1885 collected, 13 PASS / 1 inventory FAIL /
1871 NOT_RUN. Eleven newly added test cases imply 1896 only if nothing else changes;
this review did not recollect the suite and does not certify that count. Historical
Deno/dependency failures and Linux/systemd skips remain unverified here; distinguish
them and guard-envelope failures from new application defects using fresh evidence.
Installed 588/source 127 and import-adapter independent PASS retain their separate
scope. A9/A10 BLOCKED, Integrated administrative SCOPE-CLOSED, 23 operational
obligations, target/ARM64 limits and deferred Phase 11 remain unchanged.

## Preservation and stop

Post-authoring `run_review.py final-focused` passed the same **14/14**, 5.53s
console / 7.047s outer, zero failures/errors/skips and no timeout. This overlaps
the earlier 14 and adds no distinct-case credit. Final `receipt.py final` verifies
**936 of 939 inherited safe file hashes unchanged**, with only the three additive
routing notices differing; every previous byte in those documents remains. The
author's report, artifacts/final.json, test bytes, runtime, runner, installed-selection
and archive evidence remain unchanged. HEAD/branch/refs/raw index are unchanged,
staging is empty, and the only new nonignored Git path is this report. Working and
cached `git diff --check` pass (existing Git CRLF advisory messages are not failures).

Only this report and compact additive notices in the three audit routing files are
repository deliverables; reviewer scripts/receipts are retained in
[the new scratch directory](../../../scratch/a2-n1-independent-20261009-01/).
No implementation/test fix, runner change, archive change, installed-selection change,
fetch, network/Pi/production/credential access, installation, commit/push, deployment
or sandbox escalation was performed. Rollback scope is this report and the three
new notices only; preserve inherited dirty work and all historical receipts.
