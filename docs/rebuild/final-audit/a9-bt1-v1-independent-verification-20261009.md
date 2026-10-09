# A9-BT1-V1 independent local verification — 2026-10-09

**PASS for the local destination remediation, conditional on a later explicitly approved
isolated destination. Runtime A9 remains BLOCKED B1/B2/B3/D1.** No material implementation
defect was found within the authorized configuration/adapter scope. This does not activate a
recipient, approve the host, freeze a release, or establish real off-host integration.

## Inspected identity and reproducibility

- Branch `codex/rebuild-v2`; HEAD `cb54da9948370db64133a0ead6c9df89d0b61055`.
- Entry: **19 modified / 70 untracked paths**, `git status --porcelain=v1 -uall`; index empty.
  This dirty tree, including the new policy module, is the inspected implementation, not HEAD alone.
- All **16** file hashes in [BT1's manifest](a9-bt1-evidence-20261009.json), every listed inherited
  final hash, and its runner hash matched actual raw file bytes. No entry drift was found.
- Runtime overlay SHA-256:
  `e45a2dbdb59e6a0e6f3ffa6f734b3c4b8fd1c2bec05f714912d9d04f1dcf6bf1`.
  Reproduced as SHA-256 of `json.dumps(actual_files[:4], sort_keys=True,
  separators=(',', ':')).encode()`, with each object containing `path` and raw-byte `sha256`,
  manifest order, UTF-8, no final newline. This is a four-file change identity, not a release hash.
- Supplied review patch SHA-256:
  `69599627afe4ab011dabca2a64b9612a861748d3c88bb3084c83a528cc4349ae`;
  `git apply --reverse --check docs/rebuild/final-audit/a9-bt1-review-20261009.diff` passed.
- Supplied manifest SHA-256:
  `b2f41c0b0127d9ee2d415a653854ede4f4a7a0cdc0f4fd35e0757aabc5fb5aaa`.
  Runner SHA-256: `e0db037371cff2b3912900b2361b6849971f052ee0d880418346666b0364eee2`.
- The four runtime files were copied to `scratch/a9-bt1-v1-20261009/pre-change/` and only that
  copy was reverse-patched with path-filtered `git apply`. The three original modules match HEAD
  after LF normalization; the newly added policy module disappears. Live source was not reverted.
  The reviewer test then loads exact `git show <HEAD>:<path>` source into distinct temporary
  module names. Original configuration rejects isolated selection before credentials/transport;
  original store fetch records production constants. Current configuration and store record the
  selected synthetic isolated recipient instead. All transports in this negative control are fakes.
  Normalized original configuration SHA-256:
  `641e7698097cce5e7d6e75e92df752fe9e89257ebaa2f31455d95dfab05d5a73`.

## Governing clauses and scope

Exact source clauses used for this decision (line numbers refer to this inspected tree):

- `AGENTS.md:46–48`: new remote backups encrypt the complete file with `DB_ENCRYPTION_KEY`;
  “설정이 없을 때 공개 코드 저장소로 우회하지 않습니다.” Existing legacy restore compatibility remains.
- `docs/rebuild/phases/phase-08/backup-restore-contract.md:11–14`:
  “Partial/encryption/remote/audit failure preserves the previous latest pointer.”
  “Keep eight verified alternatives”. Lines 29–36 require independent isolated validation,
  a previously absent destination, cleanup and propagation of operational/cancellation faults.
- Same contract, **80–83**: “Staging may never select production. Fetch, push, independent
  readback, retention and download share one validated destination; errors never fall back to
  production. Duplicate configuration fields are rejected before credential/transport admission.”
- Same contract, **58**: “Actual key rotation/destination changes require operator decisions.”
- `deploy/runbooks/backup-verification.md:91–94`: direct store construction without a destination
  retains the production helper default; isolated callers must pass the validated destination;
  production-specific scripts “remain production-only and must not be used for isolated recovery.”
- `docs/rebuild/final-audit/a9-host-backup-boundary-decision-20261009.md:56,73` requires a typed,
  environment-bound destination and says “Before enabling a target, obtain the exact approved
  private staging repository identity”. The empty allowlist is therefore an activation prerequisite,
  not a failing local implementation. Supplied Bot-Data is production and remains excluded.
- `docs/rebuild/baseline/20-migration-plan.md:23`: “clean Raspberry Pi 5/Ubuntu 24.04 ARM64/Ethernet”
  and “no production impact”; `docs/rebuild/phases/phase-01/concurrency-failure-plan.md:41–46`
  requires dedicated staging identities, clean Pi validation and “최소 24시간 soak”.
  These gates remain unmet; this review grants no shared-host exception.
- `docs/rebuild/phases/phase-02/platform-contract.md:13–16`: cancellation does not release a
  running thread's admission; Python threads cannot be forcibly killed; incomplete shutdown
  must be reported. Transport bounds are not an interpreter-exit or remote-outcome guarantee.

Original Phase 8 “no active remote” text is historical; D22 `current/open-questions.md:133–137`
records the later production Bot-Data approval. That does not approve a staging recipient.
No external web lookup was needed or performed: governing evidence is repository-local.
No specialized artifact/app skill applied to this code audit.

## Destination trace, findings and limits

| Consumer | Verified behavior and source |
| --- | --- |
| JSON configuration | `configuration.py:110–118`: reject duplicate keys, validate environment and exact remote fields before `read_secret` at 179 or `GitTransport` at 196. Explicit production object preserved; explicit null stays local-only; absent remote is invalid. |
| Destination policy | `backup_destination.py:13,27–56`: empty source allowlist; exact production tuple or staging/isolated canonical Git SSH, fixed host/owner/ref and exact allowlist membership. Production/code repository exclusions cannot be bypassed by adding them to the test allowlist. |
| Runtime wiring | `configuration.py:198` carries the destination; `deployment.py:175–188` constructs remote only when configured; `git_backup.py:135–145` revalidates at construction and again inside the worker before workspace/credential transport work. |
| Upload/fetch/push | `git_backup.py:152–170,216–250`: direct store revalidates explicit inputs; initial fetch and one non-force push use the selected repository/ref. No fallback/retry branch exists. |
| Independent readback | `git_backup.py:251–260`: new private temporary bare repository, same fetch, commit and encrypted pair equality required; uncertain readback fails. |
| Remote retention | `git_backup.py:70–82,229–245`: validates the fetched pairs, retains latest eight plus daily points from latest seven UTC days; preserves Git ancestry and legacy paths. It uses that same selected tree and push. Envelope/digest verification here is not Fernet authentication; authenticated restore is separate and unchanged. |
| Download | `git_backup.py:262–280`: same fetch, envelope/metadata/digest checks; existing destination rejected and files created exclusively. No configured remote search/fallback. |
| Local recovery | `recovery.py:72–167`: only its configured backup root and explicit/newest candidates; decrypt/authenticate, schema/semantic and application validation; absent target required. A fresh downloaded directory must be bound explicitly to the recovery object/config. |
| Compatibility helpers | `prepare_install_sheet.py`, `verify-offhost-release.py:21,64,143`, `drill-offhost-backup.py:54,123`, `setup-backup-ssh.py` retain production-specific identity/defaults. They are not isolated recovery tools under the explicit runbook restriction above. |
| Legacy paths | V1 `database_manager.py` / `scripts/auto_backup.sh` retain their separate `DB_BACKUP_REMOTE_URL` policy; no V2 fallback into them was found. Neither was run against operational data. |

Small relevant diff excerpts:

```python
# configuration.py
remote = backup_destination.parse(value["backup_remote"], value["environment"])
backup_remote = BackupRemoteSettings(workspace, key_file, known_hosts_file, remote)
# git_backup.py
self.destination = validate(destination)
self.command(root, "fetch", "--depth=1", "--no-tags", self.destination.repository, self.destination.ref)
self.command(root, "push", "--porcelain", self.destination.repository, commit + ":" + self.destination.ref)
```

Accepted production shape remains:
`{"kind":"git-ssh","repository":"git@github.com:lgw323/Bot-Data.git","ref":"refs/heads/db-backup"}`
in `environment:production`; `backup_remote:null` works in both environments. Isolated JSON adds
`"target":"isolated"` and an exact approved repository, but none is currently enabled.

**Informational boundary, not a new defect:** omission of a low-level destination still means
production, while explicit `None`/invalid destinations fail. Such trusted helper construction is
not evidence of staging environment validation. In particular, the historical production verifier's
download call omits a destination; do not reuse its worker as an isolated recovery tool. The runtime
loader always supplies the selected destination. Arbitrary in-process mutation/monkeypatching is not
a supported security boundary. No adapter default or production constant was silently changed here.

Reviewer-owned tests independently cover the production/null/service matrix, invalid/missing and
conflicting fields, conflicting duplicate keys including non-remote objects, host/owner/ref/transport
rejection, direct construction, empty allowlist and restoration of test monkeypatches, frozen value,
approval revocation before workspace/transport effects, elapsed/short/long transport deadlines,
original-code negative controls, and real synthetic SQLite -> encrypted backup -> temporary Git ->
independent readback -> download -> authenticated restore/reconciliation/no-overwrite. That pipeline
records exactly fetch/push/fetch/fetch, all for the isolated recipient; cancellation preserves latest.

Production SSH flags/ACL ownership policy, pinned-host authentication, no agent/global-config
fallback, complete-file Fernet codec, schema 5, independent application validation and no-overwrite
logic are unchanged in the supplied patch. Focused and related fresh checks corroborate these
local invariants. `GitTransport` retains 90s total and min(30s, remaining) per child operation;
deployment closes/drains with 95s grace for configured remote work. Failed/uncertain operations
propagate without production fallback. Real timing, Linux enforcement and remote durability remain
unverified. Windows symlink tests use their existing synthetic link model, not native Linux links.

## Fresh tests (do not sum overlapping runs)

Common command prefix `P`, executed from repository root:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.venv/Scripts/python.exe docs/rebuild/final-audit/a8r4-test-runner.py -q --tb=short -p no:cacheprovider -p pytest_asyncio.plugin -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning
```

Each suffix below follows P; all temporary directories were previously absent.

| Run | Exact suffix | PASS / FAIL / SKIP | Outcome |
| --- | --- | --- | --- |
| Reviewer final | `--basetemp=scratch/a9-bt1-v1-20261009/reviewer-final-tmp tests/integration/operations/test_a9_bt1_independent.py --junitxml=scratch/a9-bt1-v1-20261009/reviewer-final.xml` | 65 / 0 / 0 | exit 0; 3.00s |
| Existing focused | `--basetemp=scratch/a9-bt1-v1-20261009/focused-tmp tests/integration/operations/test_backup_destination.py tests/integration/operations/test_git_backup.py tests/integration/operations/test_offhost_wiring.py --junitxml=scratch/a9-bt1-v1-20261009/focused.xml` | 82 / 0 / 0 | exit 0; 48.58s |
| Related | `--basetemp=scratch/a9-bt1-v1-20261009/related-tmp tests/integration/operations/test_recovery.py tests/integration/operations/test_backup_retention_contract.py tests/integration/operations/test_credential_acl.py tests/integration/operations/test_production_configuration.py tests/integration/operations/test_filesystem.py tests/integration/data/test_recovery.py tests/integration/data/test_schema_contract.py tests/unit/platform/test_executors.py tests/architecture/test_import_rules.py --junitxml=scratch/a9-bt1-v1-20261009/related.xml` | 112 / 0 / 0 | exit 0; 143.68s |

Fresh original rejection is an expected `ConfigurationError` assertion inside the reviewer negative
control, not an inherited RED receipt. The original store's production routing is also executed with
a recording fake. It does not make a real production call. Initial reviewer2 also passed 65/0/0;
after removing scratch-export dependency, baseline-final passed 1/0/0; the final run above includes
the enhanced original-store control. These overlap and are not additional independent coverage.

Initial sandbox run used P without the two warning options, plus `-o faulthandler_timeout=20`,
`--basetemp=scratch/a9-bt1-v1-20261009/reviewer-tmp`, the reviewer file and corresponding reviewer.xml.
It printed 59 dots, then stalled entering async tests and was interrupted (exit 1, no completed
test receipt). No diagnostic traceback established its exact cause. Same guarded runner outside
the sandbox completed through approved escalation, consistent with the historical socketpair
environment issue. No runner/assertion was disabled or weakened to obtain a pass.

The runner and root conftest were read before execution: dotenv/ambient app settings cleared,
repository credentials and operational data denied, application sockets denied (stdlib Windows
socketpair exempt). Existing LocalTransport checks the logical target and substitutes an owned
temporary bare repository with `protocol.allow=never` and `protocol.file.allow=always`. Import
subprocess checks independently deny network/DB/process startup. All DBs and generated keys are
temporary; no operational values were read, printed or hashed. The runner is a reviewed test
harness, not a general OS sandbox for arbitrary hostile child processes.

Documentation command: P plus `--confcutdir=tests/architecture
--basetemp=scratch/a9-bt1-v1-20261009/docs-tmp
tests/architecture/test_rebuild_documentation.py
--junitxml=scratch/a9-bt1-v1-20261009/docs.xml`.
Fresh result: **2 PASS / 1 FAIL / 0 SKIP**, exit 1, 3.26s. Heading anchors and every relative
rebuild-document link pass. The existing inventory assertion at test_rebuild_documentation.py:92
still expects the entire final-audit directory to contain only a0-phase-0-report.md. Removing this
session's new report leaves 51 inherited Markdown files and still violates that assertion. This
is the known inventory failure, not a new destination failure. The assertion and existing
documentation were not repaired or weakened. Deno was not rerun.
Full suite **NOT_RUN**: targeted destination, recovery, schema, credentials, filesystem, executor
and import checks are sufficient for this local review. Historical BT1 full-suite **1786 PASS /
2 FAIL / 27 SKIP** remains historical: inventory assertion and Deno child failure; Linux/systemd
opt-in skips and audioop deprecation warning. No clean full-suite result is claimed. No separate
lint/type/build command was invented, and no package/runtime installation was performed.

## Preservation, limits and next microphase

All runtime code, inherited tests, supplied patch/manifest/report and historical evidence are
preserved. Only a reviewer test, this report, its evidence manifest, and append-only notices in
the three current audit authorities are authorized session changes. Source/allowlist/DB/config/
credentials/services were not changed. HEAD/index remain unchanged; no stage/commit/push/reset.
Rollback removes only the three new reviewer artifacts and the precise three appended notices
after verifying their hashes/prefix lengths in the new manifest; never reset mixed inherited files.
Scratch exports/results are local reviewer artifacts and not a candidate freeze.

**NOT_RUN / NOT_PROVEN:** real GitHub/private repository visibility, scoped deploy-key privileges,
SSH server authentication, Pi/ARM64/systemd/credential mounts, installed filesystem semantics,
real remote publication/recovery/durability, representative pipeline budget/RPO/RTO, clean-host
feasibility/acceptance, pilot or >=24h soak, activation, release freeze/build/deployment,
A10/Integrated Audit/Phase11. No Discord/Gemini/YouTube or other application network call was made.

**Exactly one recommended next microphase: A9-BT2 — activation-prerequisite decision packet
(local planning only).** Acceptance requires (1) the owner naming and explicitly approving a
distinct private staging repository/ref and planned repository-scoped credentials, (2) an explicit
clean-host acceptance/feasibility decision consistent with B20/C2, with any deviation separately
approved, and (3) a reviewed list of remaining candidate-freeze, isolated integration and execution
approvals. The packet must preserve this tested identity and distinguish local evidence from future
remote/Linux evidence. Permission required: separate authorization for that planning microphase and
the owner's target/host decisions; it does not authorize allowlist edits, credentials/repository
creation, Pi access, activation or a campaign. Those actions require their own explicit scope later.
Do not freeze or deploy this candidate here. **STOP; runtime A9 remains BLOCKED B1/B2/B3/D1.**

## Final preservation receipt

Entry's 89 Git-reported inherited paths are preserved: 86 byte-identical and the three current
authority documents retain their exact entry bytes as prefixes. The four runtime files and all
16 supplied manifest targets except those three deliberately appended authorities remain exactly
as inspected. All original supplied evidence files and runner remain unchanged. Final status is
**19 modified / 73 untracked**, empty index, same branch/HEAD. Only the three reviewer artifacts
are new Git-reported paths. `git diff --check` and `git diff --cached --check` pass; existing
LF/CRLF notices only. New artifacts are checked separately for trailing whitespace.

[Final reviewer manifest](a9-bt1-v1-evidence-20261009.json) records entry and final hashes, prefix
lengths, exact test commands/XML hashes and limits. Its own hash is excluded to avoid recursion.
No concurrent checkout drift was detected across entry, pre-routing and final preservation checks.
