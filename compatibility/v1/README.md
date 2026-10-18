# Frozen V1 comparison references

`database_manager.py` is the exact LF Git blob from local commit
`6ce25d2dfd894ae340b64ebd59823d87463bbed8`, not a rewritten V2 adapter.
[manifest.json](manifest.json) records the source path, Git object, SHA256 and
original Windows-checkout hash. The package verifies the frozen source hash before
import. The scoped `.gitattributes` entry preserves LF on checkout.

This source remains necessary to demonstrate that V1's actual schema writer,
readers and backup decoder can consume isolated copies of V2 output. Comparing
V2 against itself would not establish that contract. Do not fix or modernize this
reference silently; a replacement requires a separately identified source and
explicitly updated evidence.

Only compatibility tests and `scripts/rehearse_v2_data.py` import this namespace.
The rehearsal tool redirects DB/backup paths to its temporary copies and restores
them afterward. The shared test fixture independently isolates this reference
without importing the retired root V1 runtime. No real DB, SQL backup, credential or
Music state is included here. Importing the package does not run a migration or
open a database.

This directory is outside `src`, setuptools package discovery and the ordinary
installed-release source-copy set. V2 runtime imports are forbidden by the
architecture check. Keep this source reference intentionally; it is neither an
active old bot nor a complete runnable production rollback environment. New
source exports used for offline compatibility checks must include this directory;
do not modify old frozen release archives or manifests to add it.

The selected nine Engagement/Music source files are recorded in
[oracles-manifest.json](oracles-manifest.json). Six preserve exact Git bytes;
three change only the absolute database import to this isolated namespace.
Their original and executed SHA256 values are both recorded. New package
initializers provide only namespace scaffolding and pre-import hash checks.
Do not instantiate their background tasks against Discord or real data.
Tests supply fake services and temporary paths. Startup, logging, Summary,
Watch server and the old Music Cog are deliberately absent.
