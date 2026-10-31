# Claude Opus status — Phase 01A

Status: **DONE — WAITING FOR REVIEW**. Branch `feat/resumable-loader`; PR "Phase 01A: Resumable bulk loading and consistent rollups".

* Resumable staged loader `generator/loader.py`, migrations `generator/migrations/001_loader_schema.sql` and `002_manifest.sql`. `generator/load.py` is now a Phase 00 CLI-compatible wrapper.
* Tests: 14/14 pass on a disposable local PostgreSQL 17.6 cluster (crash/kill/SIGTERM resume, retry idempotency, tamper conflict, failed activation rollback, atomic reader visibility, concurrent API writes, prefix provenance, shadow rebuild, manifest, gates).
* Bounded 1M kill/resume: 0 mismatches, activation 12.75 s, Phase 00 tenant counts reproduced. See `docs/LOADER_TEST_REPORT.md`.
* No 10M load run. No shared/benchmark/backend files changed. Phase 00 DB untouched.
* Manifest interface `loader.dataset_manifest` (v1), published on Issue #1 for Codex.
