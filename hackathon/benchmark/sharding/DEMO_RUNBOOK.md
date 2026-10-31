# Judge demo readiness (current Fedora check)

This is a staged runbook. Screen 4 is reserved for Opus's real sharding contract and is NOT READY today.

## Screen 1 — Live dashboard

Current status: **BLOCKED for a fresh verified run**. Preflight found 1.4 GiB available RAM and 3.6 GiB swap in use, with several project database containers already active. Per the resource gate, no new stack was started. Existing `round1-*` containers are from a prior isolated worktree/build, not proof of a clean current-main deployment. Do not claim live current-main dashboard verification based on them.

When resource gate passes and approved isolated config exists: show login, choose tenant A and tenant B, compare tenant-scoped summary/trends; record exact seed size and writer rate first.

## Screen 2 — PostgreSQL aggregation and refresh status

Current status: **BLOCKED for current-main deployment verification**. Use only a disposable authorized stack. Show `pgtrickle.pgt_stream_tables` configured/effective modes and `pgtrickle.pgt_refresh_history` actions, plus three local stream table names. Explain every shard owns independent stream tables/scheduler; no cross-database view is implied.

## Screen 3 — Correctness and benchmark evidence

Use `oracle.sql` independently on each shard; require zero missing and extra rows for all three stream definitions. For prior single-DB experimental benchmarks, label the actual dataset/hardware and disclose observed failures. Never present simulated Python tests as database oracle measurements. Current Codex results: 13 benchmark scaffolding tests pass; live sharding and metrics are NOT TESTED.

## Screen 4 — Shard failure and recovery (after Opus completes)

**Not ready.** Wait for Opus to publish shard mapping, API contract, and disposable network/container topology. Then use only the specifically named A-only network with `partition.sh` after reviewing its args/preconditions. Demonstrate A returns bounded 503; B read and write succeed; restore A; confirm A health and all three SQL oracles. Record times and errors. Do not use existing round1 or unrelated networks.

## Resource and evidence record

Current preflight: Fedora x86_64, 7.5 GiB RAM, 1.4 GiB available, 3.6 GiB swap used, 230 GiB disk free. Multiple unrelated/project containers already running; left untouched. New 10k/two-database run skipped because current available memory is insufficient alongside active containers.

No new Docker workload or database writes were executed for this update. No 10M test. Existing running services were not restarted or modified.
