# A9-BT1 local backup-target remediation — 2026-10-09

## Verdict and boundary

**PARTIAL: destination-routing implementation locally tested; actual isolated recipient remains
unapproved/unconfigured. Awaiting fresh independent verification. Runtime A9 remains BLOCKED
B1/B2/B3/D1.** No independent verification is claimed by the implementation author.

The user authorized only bounded local remediation and temporary-data regression, then STOP.
When asked for the isolated repository the user supplied `https://github.com/lgw323/Bot-Data`.
That is the existing production recipient, not a distinct isolated destination. It was not enabled
for staging; the released isolated allowlist remains empty. No new repository or credential was
created, and no visibility or permission claim was inferred from the URL.

Entry branch `codex/rebuild-v2`, HEAD `cb54da9948370db64133a0ead6c9df89d0b61055`, empty index,
11 modified / 65 untracked files (76 entry paths with --untracked-files=all). These are current
local observations. Recorded production source is `8e9018d4b8061cde6006eee47fa4103522f77718`,
pin `r-8e9018d4b8061cde-3dac82a792fad576`; those are historical authority records, not new Pi checks.
The worktree now contains changed runtime bytes and is **not** the unchanged cb54da9 candidate.
No freeze/archive/wheel/build/deployment identity was produced; a newly reviewed freeze is required.

## Authority and design decision

- AGENTS.md:47: “설정이 없을 때 공개 코드 저장소로 우회하지 않습니다.” Mandatory no-code-repository fallback.
- C14, backup-restore-contract.md:11–12: “Partial/encryption/remote/audit failure preserves the previous latest pointer.” (line-wrapped in source.)
- C14:14: “Keep eight verified alternatives”; C14:23: “with a 180-second unit budget.” Neither is changed.
- C14:58: “Actual key rotation/destination changes require operator decisions.”
- Host/backup boundary decision:56 proposes a typed environment-bound allowlist; :73 states
  “Before enabling a target, obtain the exact approved private staging repository identity”.
  The current user request authorizes implementing that local mechanism, not inventing a recipient.
- B20 migration plan:23 requires “clean Raspberry Pi 5/Ubuntu 24.04 ARM64/Ethernet” and
  “no production impact”; C2 concurrency-failure-plan.md:44 requires “최소 24시간 soak”.
  These runtime gates remain mandatory. A second physical Pi and the 34h campaign are proposals,
  not new mandatory requirements or established resources.

Minimal design, announced before implementation: one immutable BackupDestination, one reviewed
source allowlist, explicit isolated selector, environment binding, adapter revalidation, and the
same destination throughout Git operations. No arbitrary URL/ref acceptance or backup framework
rewrite. Production's existing explicit object and null need no operator migration. The intentional
behavior change is rejection of formerly accepted staging-to-production remote configuration.
Duplicate keys anywhere in the operations configuration are also rejected to remove ambiguity;
other read_json callers retain their prior default behavior.

## Destination trace and root cause

| Path | Before | Result |
| --- | --- | --- |
| load_settings | Exact production dictionary comparison, regardless of environment | Shared parse/validate policy before secrets/transport; null explicit local-only |
| BackupRemoteSettings | Workspace/key/known-hosts only | Adds immutable destination |
| deployment.backup_once | Constructs GitRemoteBackup only when configured | Same wiring; selected destination retained |
| GitRemoteBackup | Constructs store with no destination | Revalidates and passes destination before workspace/transport effects |
| GitBackupStore.fetch | Module production REMOTE/REF | Selected repository/ref for upload base, independent readback and download |
| GitBackupStore.publish | Push production REMOTE/REF | Selected repository/ref; one non-force fast-forward; no retry/fallback |
| Remote retention | Reads/prunes fetched tree | Same selected tree; eight/latest-seven-UTC-days policy, ancestors and legacy preserved |
| GitBackupStore.download | Production fetch, absent output required | Selected destination; absent output and envelope/digest checks unchanged |
| Backups.candidates/restore | Configured local backup root | Unchanged; explicit independent download then separate recovery-root config; no remote search |

Duplicated runtime production constants were consolidated in backup_destination.py; git_backup.py
re-exports REMOTE/REF for existing callers. Low-level store construction without a destination
retains its existing production-helper default; an explicit invalid/None destination fails instead
of defaulting. Runtime isolated configuration never uses the omitted-argument path.
Production-only helpers prepare_install_sheet.py, verify-offhost-release.py, setup-backup-ssh.py
and drill-offhost-backup.py retain their production literals/defaults and are not staging tools.
Legacy database_manager.py/scripts/auto_backup.sh use V1 DB_BACKUP_REMOTE_URL policy and were not
changed or executed. There is no V2 environment-variable fallback to those paths.

Interface:

```python
BackupRemoteSettings(workspace, key_file, known_hosts_file, destination)
GitBackupStore(transport, workspace, destination)
# Fetch and push now use destination.repository and destination.ref.
```

Illustrative config fragment (NOT RUNNABLE: placeholder rejected and allowlist empty):

```json
{
  "environment": "staging",
  "backup_remote": {
    "kind": "git-ssh",
    "target": "isolated",
    "repository": "git@github.com:lgw323/<approved-private-repository>.git",
    "ref": "refs/heads/db-backup"
  }
}
```

Exact source review and owner approval are the trust boundary; an operator cannot extend approval
through JSON. Only canonical scp-style git SSH, github.com, lgw323 owner, fixed db-backup ref and
exact allowlisted repository are accepted. Production/code repositories remain excluded even if
accidentally placed in the isolated allowlist. Unknown, missing, duplicate, conflicting, malformed,
option-like, traversal, unsupported protocol/host/owner/ref inputs fail before transport.
Private visibility and repository-scoped key privileges cannot be proven by syntax; later operator
evidence and execution approval are still required. Existing SSH ACL/ownership, pinned host,
no agent/global config fallback, encrypted authentication, schema, backup atomicity, latest pointer,
verified retention, restore isolation, 90s/30s transport bounds and executor cancellation/drain remain.

## Reproduction and fresh local evidence

The original implementation was tested before runtime edits with
`test_explicit_isolated_destination_survives_configuration`: **0 PASS / 1 FAIL / 0 SKIP**, exit 1,
`ConfigurationError: unapproved remote backup configuration` at original configuration.py:120.
A fake GitTransport guarded that boundary; rejection occurred before its construction. This RED
is expected rejection of an explicitly selected isolated target, not observed production routing.
The test's conditional policy fixture only supplies a synthetic allowlist when the new module
exists; it does not patch configuration or destination routing. Tests never approve a real target.

Initial harness attempt: 1 setup ERROR due to sandbox default temporary-directory permissions;
a fresh owned --basetemp yielded the real RED above. Initial focused and diagnostic runs then
stalled in Windows asyncio's internal _fallback_socketpair/accept; diagnostic faulthandler after
20s identified event-loop setup before the test body. Both owned sessions were interrupted.
Approved unsandboxed runs retain the same credential/data/network-denying runner; only stdlib
socketpair is exempt. No assertions or environment-failure tests were softened or skipped.

Fresh command results are appended below after completion. Selections overlap; do not sum them.

## Isolation, preservation, review material and limitations

The reused a8r4-test-runner.py installs root conftest credential denial, clears inherited application
configuration without printing values, disables dotenv, denies repository operational data and
application sockets. Temporary fixture DBs/keys only. Local Git transport checks the exact expected
logical recipient, substitutes an owned temporary bare repo, and sets protocol.allow=never plus
protocol.file.allow=always; it cannot contact SSH/HTTPS destinations. Child-process cases were
inspected: import-only no-side-effect probes, synthetic canaries/SQLite/worker lifecycle, local Node
client harnesses and provider --version; Linux/systemd tests retain their explicit opt-in skips.
Root tests/conftest routes legacy DB/backup paths to temporary fixtures. No browser campaign runs.

No Pi, GitHub, production remote traffic, real DB/config/service, credentials, package installation,
commit, stage, push, reset, cleanup, deployment, pilot/soak, A10/Integrated Audit or Phase11 action.
The preservation entry snapshot covers only Git-reported repository paths and explicitly selected
source/doc files; operational data/secrets were neither collected nor hashed. Full entry-relative
diff and final hashes accompany this report; mixed docs are appended, never bulk-reverted.

Remaining limits: empty isolated allowlist; independent implementation/security review; owner
confirmation of a different private destination and scoped credentials; newly reviewed candidate
freeze; clean-target/shared-host feasibility; actual Linux/ARM64 credential/service behavior;
real remote durability and full pipeline timing/RPO/RTO; B1/B2/B3/D1 and actual execution approval.
Historical inventory/Deno failures, Linux skips and audioop warning are not silently removed.
No separate configured lint/type/build command exists in pyproject.toml; these checks are NOT_RUN.

Exactly one recommended next microphase: **A9-BT1-V1 fresh independent local verification**.
Review the entry-relative diff, hashes, RED and local evidence; independently reproduce routing,
security rejection, compatibility, retention/recovery/failure bounds and preservation. Accept only
if no fallback or security regression exists and claims remain limited to tested local behavior.
Treat the empty allowlist and Bot-Data response as an open activation prerequisite, not approval to
contact production. Separate authorization is needed to start that review; no Pi/network/deployment,
recipient creation, freeze or campaign is included. Runtime A9 remains BLOCKED. STOP.

## Preserved RED test revision

The original RED command selected this initial revision of
`tests/integration/operations/test_backup_destination.py`; later policy/fault cases were added to
that file. Use the preserved executable body below (comments/docstring omitted) in that test-package location
in a disposable baseline checkout
for a negative control. Do not mistake later imports of the new policy module for the original RED.

```python
import json
from discordbot.operations.adapters.configuration import load_settings
from .test_runtime import config_files

ISOLATED = "git@github.com:lgw323/A9-BT1-Synthetic.git"
ISOLATED_CONFIG = {"kind": "git-ssh", "target": "isolated", "repository": ISOLATED,
                   "ref": "refs/heads/db-backup"}

def test_explicit_isolated_destination_survives_configuration(config_files, monkeypatch):
    from discordbot.operations.adapters import configuration
    policy = getattr(configuration, "backup_destination", None)
    if policy is not None:
        monkeypatch.setattr(policy, "ISOLATED_REPOSITORIES", frozenset({ISOLATED}))
    file, credentials = config_files
    value = json.loads(file.read_text())
    value["backup_remote"] = ISOLATED_CONFIG
    file.write_text(json.dumps(value))
    calls = []
    monkeypatch.setattr("discordbot.operations.adapters.git_backup.GitTransport",
                        lambda *args: calls.append(args))
    settings = load_settings(file, credentials, "operations")
    assert settings.backup_remote.destination.repository == ISOLATED
    assert settings.backup_remote.destination.ref == "refs/heads/db-backup"
    assert calls == [(credentials / "backup_ssh_key", credentials / "known_hosts")]
```

## Entry-relative rollback

Remove only the A9-BT1 additions/diffs listed in the review patch after confirming their hashes;
restore this session's changed runtime/test/runbook bytes from the entry snapshot, not whole-tree
HEAD. The four inherited mixed documents retain their exact entry bytes as prefixes, so remove only
the appended A9-BT1 paragraphs. Other newly changed contract/config-guide docs are also append-only.
Never reset inherited files, remove tracked SQL/backups, or run cleanup against data/history.
This is a local rollback procedure, not an executed rollback or production procedure.

## Exact changed-file review identity

The entry-relative [review patch](a9-bt1-review-20261009.diff) contains only the following
14 implementation/test/contract/routing changes, including append-only changes inside mixed docs.
The report and generated evidence manifest are additional new evidence files. Hashes are raw
worktree bytes, not Git LF-normalized blobs. No candidate release freeze is implied.

| File | SHA-256 |
| --- | --- |
| `src/discordbot/operations/adapters/backup_destination.py` | `b661405b356493142902c900d63f6dae81594f192fef0b6e20f7ac0728526688` |
| `src/discordbot/operations/adapters/configuration.py` | `ffa26abb232a6d95bad75686506f9d266f060189c965c7e6471c07d18533a5be` |
| `src/discordbot/operations/adapters/filesystem.py` | `795337af6920653392d631c6acba6003024ba8b1846daaf007b95c36d2b18049` |
| `src/discordbot/operations/adapters/git_backup.py` | `3cf29354e84c6a477e643016b84a9d7b771454bb8066c1584428eac5d332069b` |
| `tests/integration/operations/test_backup_destination.py` | `451baad3f2110eeae38021df8589759b1edba902b91d8122830932312521e079` |
| `tests/integration/operations/test_git_backup.py` | `d737030b5cf943811412781620be4e6c44712cb549fd58f16958172b42bff747` |
| `tests/integration/operations/test_offhost_wiring.py` | `8ad4c1cbefb341e7891d54b5b29f79b88a6979e545b16a4fcb5b8334e11c94b8` |
| `CHANGELOG.md` | `6ea6624fc76f444ceb584bb2170ace8b0db67a9b5c7e4c8993548882ebe8fab6` |
| `deploy/runbooks/backup-verification.md` | `3eb3c99cd9db970400c233da2490db8cbefeb1c8515d2dc097869b6949e34527` |
| `docs/rebuild/phases/phase-08/backup-restore-contract.md` | `692f27f4a64503a7f23359c9887e2fe0aab9920ffe1e9463158a3d2f00dcefcb` |
| `docs/rebuild/phases/phase-10/config-migration-guide.md` | `86e3e7b539c06e64b623d2e06fda2cc1fe99dca035934fe694b325972661ecd7` |
| `docs/rebuild/current/final-audit-active-state.md` | `b8a0500b7d3be7505e294a4723f141d454ebfc1f7b3b3046b6d72520574466d9` |
| `docs/rebuild/current/final-audit-ledger.md` | `d862b3862848468761d4dd43c83872202a2543a834b1e24f414d0a8fd4eab654` |
| `docs/rebuild/current/final-audit-document-index.md` | `36d6a15d847e8500847b3b0c6d0ff9d0c12ea99fb9ad568d554e8c0d02e3ebbf` |

Runtime overlay SHA-256: `e45a2dbdb59e6a0e6f3ffa6f734b3c4b8fd1c2bec05f714912d9d04f1dcf6bf1`.
Computed over the above four src entries in listed order, compact UTF-8 JSON with sorted object keys,
separators comma/colon, no trailing newline. This identifies the change only, not a complete release.

Patch SHA-256: `69599627afe4ab011dabca2a64b9612a861748d3c88bb3084c83a528cc4349ae`.
Inherited preservation: 72/76 entry paths byte-identical; CHANGELOG, active-state, ledger and
document-index preserve exact entry bytes as prefixes. Browser fixture and all other inherited
untracked files are unchanged. HEAD/index unchanged. Git diff --check and cached --check PASS;
only existing LF/CRLF conversion notices. New untracked files also checked for trailing whitespace.

## Completed fresh test results

All commands use `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'`. `P` below expands exactly to:

```text
.venv/Scripts/python.exe docs/rebuild/final-audit/a8r4-test-runner.py -q --tb=short -p no:cacheprovider -p pytest_asyncio.plugin
```

Each test run uses its own previously absent `--basetemp` under
`scratch/a9-bt1-20261009/`; XML outputs are in that same directory. `S` expands to
`-W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning`.
These are actual fresh results, not historical results. The selections overlap.

| Run | Command after P | PASS | FAIL | SKIP | Outcome |
| --- | --- | ---: | ---: | ---: | --- |
| Pre-change RED | `--basetemp=scratch/a9-bt1-20261009/red-tmp tests/integration/operations/test_backup_destination.py --junitxml=scratch/a9-bt1-20261009/red.xml` | 0 | 1 | 0 | exit1, expected configuration rejection, 2.86s |
| Focused | `--basetemp=scratch/a9-bt1-20261009/focused2-tmp tests/integration/operations/test_backup_destination.py tests/integration/operations/test_git_backup.py tests/integration/operations/test_offhost_wiring.py --junitxml=scratch/a9-bt1-20261009/focused.xml` | 74 | 0 | 0 | exit0, 41.21s |
| Final policy incl. eight added boundary cases | `--basetemp=scratch/a9-bt1-20261009/policy-final-tmp tests/integration/operations/test_backup_destination.py --junitxml=scratch/a9-bt1-20261009/policy-final.xml` | 55 | 0 | 0 | exit0, 1.35s |
| Related | `S --basetemp=scratch/a9-bt1-20261009/related-tmp tests/integration/operations tests/integration/data tests/architecture/test_import_rules.py --junitxml=scratch/a9-bt1-20261009/related.xml` | 973 | 0 | 0 | exit0, 352.97s; collected before the final eight policy cases were added |
| Full final source | `S --basetemp=scratch/a9-bt1-20261009/full-tmp tests/ --junitxml=scratch/a9-bt1-20261009/full.xml` | 1786 | 2 | 27 | exit1, 382.28s; includes all final cases |

Documentation command: same runner, `-q --tb=short -p no:cacheprovider --confcutdir=tests/architecture`
and the two nodes in tests/architecture/test_rebuild_documentation.py:
`test_heading_anchor_preserves_spaces_around_removed_punctuation` and
`test_all_relative_rebuild_document_links_resolve`, with `--junitxml=scratch/a9-bt1-20261009/docs.xml`.
Result **2 PASS / 0 FAIL / 0 SKIP**, exit0, 3.94s; one Unknown config option asyncio_mode warning
because that documentation-only invocation did not load pytest-asyncio. No assertion was softened.
A final documentation-only rerun after completing this report uses the plugin and is recorded in
the evidence manifest.

Full-suite failures (same known test nodes; no new backup failure):

1. `tests/architecture/test_rebuild_documentation.py::test_rebuild_documents_are_partitioned_without_loss`,
   line92: still expects the final-audit directory to contain only a0-phase-0-report.md; existing
   A4/A6/A7/etc. documents already contradict it. New audit evidence also lies outside that stale set.
2. `tests/integration/music/test_resources.py::test_pinned_provider_and_runtime_load_without_network`,
   line178: Deno --version child fails with ExternalPermanentError. No dependency/runtime installed,
   upgraded or test skipped to hide this environment failure.

The 27 skips are opt-in Linux/systemd termination cases on Windows. Full suite emitted one
DeprecationWarning for audioop removal in Python3.13. RuntimeWarning/unraisable warnings were errors.
Historical 1673/2/27 and 1652/3/27 counts in the A9 packet are NOT this run; the historical third
artifact-ordering failure did not recur in the final full run. No clean full-suite PASS is claimed.

Coverage evidence: final policy55 tests check approval/owner/transport/ref/environment boundaries,
explicit null/missing/duplicate fields, before-subprocess rejection, adapter revalidation and
one-attempt bounded failures. Parameterized local Git tests exercise both production and isolated
routing through publish/base fetch/readback/download, old-artifact retention, immutable collisions,
no-force ancestry and no-overwrite. Both targets preserve latest on real temporary-DB backup failure.
Related operations/data suites retain authentication, schema, restore, retention, timeout/cancellation
and import-side-effect assertions. Local Git/synthetic fixtures do not establish remote durability.

**NOT_RUN:** Pi/ARM64/installed systemd/SSH credential mounts, actual repository privacy or key scope,
real off-host publication/recovery/180s pipeline timing/RPO/RTO, build/wheel/deployment, representative
pilot/24h soak, independent verification. No configured separate lint/type command was invented.

Final artifacts: this self-contained report, entry-relative review diff, and
[auditable hash/preservation/test manifest](a9-bt1-evidence-20261009.json). Final status is
19 modified / 70 untracked paths, index empty, HEAD/branch unchanged (including new evidence files).
The 17 session-owned changed paths are the 14 in the hash table plus these three evidence files.
The review patch reverse --check passes; no rollback was actually applied.
**STOP: A9-BT1 remains PARTIAL pending a distinct target and independent verification;
runtime A9 remains BLOCKED B1/B2/B3/D1, with host feasibility and actual execution approval outstanding.**
