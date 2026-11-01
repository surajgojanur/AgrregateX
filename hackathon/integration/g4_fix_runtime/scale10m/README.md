# G4 fix at 10M orders / 10 tenants

The same 22 change histories as `../cases.sql`, run on **10,000,000 synthetic orders across 10 tenants** (seed 42, uneven tenant sizes: tenant 1 has 3.4M orders and tenant 10 has 0.34M). They run on a throwaway native PostgreSQL 18.6 with the **patched** pg_trickle (`pg_trickle.dylib` sha256 `6867f6bc…`).

| File | What it does |
|---|---|
| `run10m.sh` | Starts a private database (127.0.0.1:55432), generates the data, builds the 3 summaries, runs the full 10M check, the 22 cases, the full 10M check again, and the tenant-isolation check. A watchdog stops everything if free disk falls below 4 GB or free swap below 512 MB (limits approved by the operator). |
| `cases10m.sql` | Generated from `../cases.sql`. New orders get IDs above 20,000,000, so they can't collide with the generated 1–10M. Cases that change existing orders use real orders picked by `pick.sql`. |
| `pick.sql` | Picks real tenant-1 and tenant-2 orders inside the window the cases write to (2026-09-01 … 09-06). |
| `scoped_oracle.sql`, `check10m.sql` | After each case: an exact source-vs-summary check for tenants 1–2 over that window, so it's fast at 10M. |
| `oracle_lowmem.sql` | The full exact check of all 10M rows, before and after the cases (copied from `main`). |

## Runs
| Run | Result |
|---|---|
| `smoke-50k` (same scripts, 50,000 orders) | **22/22 cases correct**; full check 0/0 before and after; tenant isolation 4/4 |
| `attempt1-stopped-low-memory` (10M) | **Stopped by the watchdog, not a test result.** All 10M orders were generated in 96 s. While the summaries were being built, free swap fell to 502 MB (Docker Desktop was also running), so the database was shut down cleanly. No case ran. |
| `patched-10m-10t` (10M, retry) | **Running.** Docker is quit, and the summaries are built sort-based so they spill to disk instead of RAM. Results will be added here. |
