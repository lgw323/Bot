# P11 publication preparation — 2026-10-18

**A normal, no-force publication is possible, but it includes existing V2 history
as well as P11. Nothing has been staged, committed, pushed or merged.**

## Verified destination and history

Configured fetch and push destination is the public repository
[`lgw323/Bot`](https://github.com/lgw323/Bot), `https://github.com/lgw323/Bot.git`.
No embedded credential was present in the configured URL. Normal Git fetch and
GitHub CLI metadata reads succeeded without new credentials or authentication.
The default fetch refspec only covered `main`; the existing V2 branch was then
fetched explicitly into its remote-tracking ref without changing configuration.

| Ref | Observed commit | Relationship to local HEAD |
| --- | --- | --- |
| Local `codex/rebuild-v2` | `6ce25d2dfd894ae340b64ebd59823d87463bbed8` | Current unchanged HEAD |
| Remote `codex/rebuild-v2` | `75e0e7808f77fe35db9608bd7b22cae0dddcb8f3` | Ancestor; 0 remote-only, 77 local-only commits |
| Remote/default `main` | `8432fdef40cddc131176fa875e350660dc897e12` | Ancestor; 0 main-only, 220 local-only commits |

The 77 newly public commits contain 28 fixes, 15 test commits, 33 documentation
commits and one chore. They cover V2 lifecycle/cleanup, SQLite admission,
Engagement/Summary/Watch/Music fixes, backup/retention, source/installed verification
and their historical evidence. They are separate from the new P11 changes and
cannot be omitted from a fast-forward push of this branch. No unrelated project
files were identified in their path inventory. The final diff from the existing
remote V2 branch is 339 files, 58,521 insertions and 434 deletions before P11.
Integrating into `main` includes all 220 existing commits before new P11 commits;
143 of these are already reachable on the remote V2 branch.

Both remote branches reported `protected: false`; `main/protection` returned
“Branch not protected” (404), and the repository ruleset list was empty. The
authenticated account has push/admin permission. All seven returned PRs were
closed/merged; there is no open PR to update. These observations do not authorize
publication or bypass a later protection change.

## Review results and boundaries

- The P11 source/test change is coherent: 26 original paths and 19 V1-only test
  files removed, retained consumers use explicit references, and the credential
  canary no longer depends on the retired startup module. Exact removal/recovery
  details are in the [retirement result](p11-v1-removal-result-20261018.md) and
  [manifest](p11-v1-retirement-manifest-20261018.json).
- The frozen DB matches its local Git blob byte-for-byte. All nine Engagement/
  Music references match their recorded Git originals after only the documented
  absolute DB import substitutions. The LF attributes cover the hashed Python
  and oracle manifest files. Package discovery remains limited to `src`.
- The working-tree `src/` diff and Git index are empty. Existing P11 evidence is
  reused: **172 focused tests passed; 1897 tests collected**. No new runtime test,
  full suite, host audit or cancelled deployment gate was reintroduced.
- A bounded credential-pattern scan covered 493 newly reachable historical text
  blobs, including intermediate history, and 171 current changed/untracked text
  files. Its 13 matches are exact copies of a rejected synthetic loopback URL
  parameter in `test_control_client_rejects_non_literal_loopback_or_ambiguous_url`,
  recorded in test evidence. No actual credential finding remains. This is a
  heuristic scan, not a guarantee against arbitrary secrets.
- No new historical DB/SQL/credential/binary path required exclusion from the
  history scan. Operational `.env`, DB, SQL backups and production logs were not
  read. Existing Git history and tracked audit evidence were not removed.
- Exclude all 40 untracked `docs/rebuild/gpt_handoff` artifacts (ZIP plus 39 files,
  644,531 bytes total). They are generated handoff copies; their contents were not
  needed or reviewed for publication. Leave them locally intact.
- Inherited cutover/WAL tools, ARM64 smoke tooling, browser scripts, their tests,
  formal-release/audit documents and invite guidance remain separate. Do not
  silently add them because their paths appear in the same working tree.

## Exact proposed commits

### 1. `refactor: retire V1 runtime and isolate compatibility references`

Use the 94 whole-file paths in the reviewed P11 scope (including the exact 45
deletions, compatibility sources, consumers/tests, source export policy, result
and recovery manifest), plus P11-only versions of these five shared documents:

- `README.md`: local V2 setup/source boundary; exclude the unrelated invite-guide row.
- `CHANGELOG.md`: the final V1 retirement section only; exclude the earlier
  intermediate checkpoints and inherited release/WAL/ARM64/Watch entries.
- `docs/operations.md`: current source-path retirement notice only.
- `docs/product-spec.md`: current V2 source-boundary notice only; preserve the
  separate inherited Watch acceptance edit outside this commit.
- `docs/rebuild/baseline/01-current-system-overview.md`: the single deleted-source
  link repair, preserving the historical description.

This is **99 paths**. Implementation, fixtures, tests and required execution
instructions must stay together so the resulting commit collects independently.

### 2. `docs: publish final P11 cleanup and publication status`

Publish this report and a concise current P11/publication notice on the HEAD
versions of these three tracked files:

- `docs/rebuild/current/current-plan.md`
- `docs/rebuild/current/final-audit-active-state.md`
- `docs/rebuild/current/final-audit-ledger.md`

This is **4 paths**. The notice links only the included report/result/manifest.
The much larger inherited checkpoint additions are not part of this commit.
Untracked compact/index/prior P11 documents remain local evidence pending their
own portable-document publication: several currently contain ignored `scratch`
links or editor-specific `:line` links, and some depend on unpublished formal-release
documents. Do not publish those files wholesale or add scratch to repair their links.

The exact file lists, SHA256-bound proposed contents and non-applied patches are
in `scratch/p11-publication-review-20261018-01/`. `commit-1.patch` and
`commit-2.patch` are proposals, not staged changes. Shared-file versions deliberately
exclude unrelated inherited hunks without editing or discarding the live files.

## Recommended update strategy

1. Parent approves the public destination and inclusion of the **77 pre-existing
   unpublished commits**, then reviews the two exact P11 commit proposals.
2. Recheck remote tips immediately before publishing. Stage only the reviewed
   paths/hunks, inspect the staged content, and make the two atomic commits.
   Preserve unrelated live work. No blanket `git add .` and no history rewrite.
3. Fast-forward `origin/codex/rebuild-v2` with a normal push. If the remote changes,
   stop to inspect divergence; do not add force flags.
4. Open a draft PR from `codex/rebuild-v2` to `main`, explicitly describing the full
   V2 integration scope plus P11, the reused validation and remaining limitations.
   A branch push alone does not update GitHub's default `main` view.
5. After the requested review/merge authorization, use a normal merge preserving
   existing commit identities. Updating `main` this way achieves the cleaned V2
   default tree without force push or deleting historical evidence.

No runtime activation, Pi restart, migration, dependency upgrade or another broad
audit is required by this publication preparation. The existing source identities
and recorded evidence must remain explicit; do not turn unexecuted tests into PASS.

## P11 status and remaining work

Local V1 source retirement is complete. Installed release cleanup remains
**9 of 12 deleted, 3 retained plus 4 separately protected** at the last remote
receipt (October 18, 07:37 UTC). The three remaining releases and five exact audit
fields remain a separate bounded task; no additional remote deletion is authorized
by this report. Accepted cancelled tests and outstanding observations are not
relabelled as completed. No Pi health update is claimed from GitHub metadata reads.

Publication is **prepared, not executed**. There is no denied operation, pending
credential prompt or uncertain push. The remaining decision is the parent's
approval of the explicit public history/scope and eventual PR merge; it is not
a new runtime audit gate.
