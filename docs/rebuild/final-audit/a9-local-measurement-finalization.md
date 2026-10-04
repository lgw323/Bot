# A9 local measurement milestone finalization

2026-10-04. **Local measurement milestone complete. A9-LOCAL-M2 independently
CLOSED; M1 closure retained. Runtime A9 remains BLOCKED B1/B2/B3/D1.**
The [independent M2 verification](a9-local-m2-independent-verification.md) is the
closure authority. Earlier author pending-review and independent FAIL records
remain historical, unchanged. This finalization starts no new microphase.

## Reviewed chain and checks

The owned patches for [candidate measurement](a9-candidate-local-report.md),
[M1 remediation](a9-local-m1-remediation-report.md),
[M2 remediation](a9-local-m2-remediation-report.md) and
[recovery reconciliation](a9-recovery-reconciliation-report.md) were reconstructed
from their recorded before/after bytes and matched exactly. Independent candidate
[M1 discovery](a9-candidate-local-independent-audit.md),
[M1 verification/M2 discovery](a9-local-m1-independent-verification.md) and M2
closure remain separate records. No vulnerable intermediate implementation is
introduced as a new commit; the final tested code and its tests are one unit.

Independent closure checks: **126 focused PASS, 20 independent saved-reader PASS,
original M1 attack 1/1 PASS, M2 deletion attack 1/1 PASS, documentation 2/2 PASS**.
These are the independent report's runs, not newly executed by finalization.
Author M2 checks remain 126 focused, 41 relevant, one capture, both attacks and
two documentation checks. No repeated full suite or regenerated measurement is
needed for scoped documentation/staging. Fresh finalization document link checks
are retained in `scratch/a9-local-finalization/docs.xml` and `docs-final.xml`; exact committed paths,
commit IDs and final hashes are returned in the handoff.

Four dependency mismatches remain: bgutil-ytdlp-pot-provider pin 1.3.1, deno pin
2.9.7 and yt-dlp-ejs pin 0.8.0 have no installed distribution version; yt-dlp
installed 2026.7.4 differs from pin 2026.8.19. Known inventory/Deno failures and
historical full-suite **1673/2/27** and **1652/3/27** PASS/FAIL/SKIP, including the
artifact-ordering failure, remain. No clean-suite, wheel/ABI or ARM64 claim.

## Commit ownership and historical identity

Three logical local commits are prepared: recovery reconciliation documentation;
the final candidate adapter/harness/packet verifier and their tests; then the full
local evidence/independent-review chain and compact closure routing. Mixed tracked
documents receive only owned hunks staged against HEAD. Earlier audit, Watch and
other inherited edits remain unstaged and byte-preserved.

The entire `docs/rebuild/current/final-audit-document-index.md` predates this chain
as an inherited untracked file. Its unrelated contents cannot be adopted safely.
Only the recovery appendix and local closure appendix are recorded as
`a9-recovery-document-index.patch` and `a9-local-measurement-document-index.patch`.
The working index stays untracked; this is a deliberate ownership limitation,
not an omitted implementation or local report. Pre-existing untracked Phase 10
and A0-A2 documents remain inherited prerequisites of older authority links;
they are not silently included in these commits.

All twelve local candidate/M1/M2 reports, manifests and evidence files, including
the three independent reports, are included. Recovery report is also included.
OS-temp independent probes and ignored scratch XML/patch/baseline receipts remain
local supporting material at the paths/hashes recorded by those reports; the
committed aggregate evidence records their results. They are not promised to be
available in a fresh checkout. No scratch/credentials/DB/data/log/cache is staged.

All three manifests are **historical measurements at HEAD
`769a00ab892edc7f98a1f9d947abd23d99c1056a`**. Finalization commits change HEAD;
`verify_packet()` must consequently reject reusing them as current identity.
The committed files preserve the original hashes, observations and flags without
retroactive edits. A future measurement would need its own authorized scope.
Newest historical M2 manifest SHA-256:
`387b6406aef0715be01aa0279c50e1babde94b2cf14db83d44e222d5cc12dad3`;
frozen export `573d85f550a705146c0f20a7fc1f360ab3b5b1ffdf1d6157da605db4f19a8eb7`.

Git's existing text normalization stores CRLF JSON artifacts as LF blobs. Original
working-file bytes and their recorded hashes are untouched; committed JSON values,
canonical source/receipt digests and observations are identical. Original artifact
byte hashes must not be confused with normalized Git blob SHA-256. For the M2
manifest, Git LF SHA-256 is
`c3369b34c0c3bf49925926a95390e1b6a2b2d1995a051d41736979aedfab5c21`;
the original CRLF artifact hash remains the one above. The final hash inventory
records both identities for every committed file. No historical receipt is
regenerated or relabeled as a measurement of the later commits.

## Rollback and boundary

Each commit body records validation and rollback. Revert the documentation commits
independently if routing/evidence packaging must be withdrawn. Reverting the code
commit restores the prior fake-only harness and removes the candidate adapter,
packet verifier and packet tests; historical reports remain history. Do not reset
or restore whole mixed working files, remove prior reports or rewrite history.

Runtime B1 workload/SLO, B2 representative >=24h soak, B3 host/ARM64/services and
sustained recovery proof, and D1 completion routing remain BLOCKED. No Watch/music
packet, Pi/SSH/network/provider campaign, install, credentials, permission,
deployment, architecture work, A10, Integrated Audit or Phase 11 starts here.
Local commits only; no push. **STOP after this milestone finalization.**
