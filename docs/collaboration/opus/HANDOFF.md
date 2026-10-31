# Claude Opus handoff — Phase 01A

## Delivered

* `generator/loader.py`: plan → stage (batch commits + checkpoints + rollup deltas) → verify-stage → atomic activate → finalize, plus `status`, `verify-rollups`, `rebuild-rollups`, `manifest` and `abort`. Re-running `load` resumes.
* `generator/migrations/`: loader-only schema `loader` (runs, batches, stage, deltas, validations, `dataset_manifest` view). No public schema change.
* `generator/load.py`: wrapper for `load.py 1000000 10` / `load.py 10000000 100`, which `scripts/verify.sh` still calls.
* `generator/tests/test_loader.py`: 14 tests; they need `LOADER_TEST_ADMIN_DSN` pointing at a **disposable** cluster.
* `docs/LOADER_DESIGN.md`, `docs/LOADER_TEST_REPORT.md`, `docs/collaboration/opus/G3_OBSERVATIONS.md`.

## For the integration owner

1. Review the PR. Do not merge without review.
2. Before any 10M run:
   * install `psycopg[binary]==3.2.3` on the Fedora host;
   * run the test suite against a throwaway PostgreSQL 18.6 container, not the 1M volume;
   * decide **fresh 10M/100 volume vs prefix extension** of the 1M baseline (tenant-domain caveat in LOADER_DESIGN.md);
   * schedule a write maintenance window for activation (reads continue).
3. Gated command: `AGRREGATEX_LOADER_ALLOW_FULL_SCALE=1 python3 generator/loader.py load --rows 10000000 --tenants 100 --allow-full-scale [--prefix-rows 1000000 --prefix-tenants 10]`, then `verify-rollups` and `manifest`.
4. Shared files untouched that may want follow-up after agreement:
   * README.md and scripts/verify.sh still document `load.py` (it still works);
   * `database/rebuild.sql` remains the Phase 00 full-downtime rebuild (`loader.py rebuild-rollups` is the readers-online alternative).

## For Codex

Consume `SELECT manifest FROM loader.dataset_manifest` (owner role); the fields are listed in LOADER_DESIGN.md. Loader exit codes: 0/1/2/3/130.

## Not done / unverified

* 10M load and its timings.
* PostgreSQL 18.6, Podman and cgroup limits.
* The official generator.
* Online (non-write-blocking) shadow rebuild.
