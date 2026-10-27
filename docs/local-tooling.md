# Local cutover tooling and guarded tests

The local cutover prototype exercises the existing deployment and storage adapters
with synthetic temporary databases and fake host/service adapters. It does not
change application startup, production configuration, database policy or deployment
entrypoints. `Plan.validate` rejects live mode and `LiveExclusion` always refuses.

Keep the controller, byte-pinned `stopped_wal.py`, `cutover_model.py`, regression
tests and `tests/support/cutover_local_worker.py` together. The worker requires a
fresh empty fixture directory with a per-launch ownership marker. It denies
credentials and application network access and restricts SQLite to that fixture.
Its credential boundary also works in an installed candidate layout without the
source checkout's root `conftest.py`.

Use a Python 3.12 environment with the repository's existing development
dependencies, from the repository root. Choose new temporary paths for each run:

```powershell
python -B scripts/run_guarded_tests.py tests/integration/operations/test_cutover_controller.py tests/integration/operations/test_stopped_wal_helper.py -q -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning -o xfail_strict=true --basetemp=../cutover-test-tmp
python -B scripts/run_guarded_tests.py tests/ -q -p no:cacheprovider -W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning -o xfail_strict=true --basetemp=../full-test-tmp
```

The runner disables automatic dotenv loading and bytecode writes, clears inherited
application settings, denies protected repository data and application networking
in the pytest process, and permits the Windows stdlib event-loop socket pair.
Python audit hooks are process-local; this is a boundary for reviewed tests, not an
OS sandbox for arbitrary code. Child tests must retain their own isolation.
The older hash-bound audit runner remains historical evidence. Focused checks do
not replace the full source suite or installed admission.

The tests cover sequencing, continuous ownership, backup equivalence, same-inode
WAL normalization, interrupted workers and honest uncertain outcomes. See the
[WAL helper contract](../deploy/tools/stopped-wal.md) for preservation and failure
semantics. These local results do not prove Linux consumer exclusion, native ARM64
behavior, installed operational gates or current Pi health.

This publication intentionally leaves dated host/transport/worker templates,
fixed-release ARM64 campaigns, live browser QA scripts, large audit narratives,
handoff exports and local workspace receipts outside the selected changes. Existing
main publication and closure records remain authoritative. Any later host execution
needs its own reviewed target and authorization; publication is not deployment.
