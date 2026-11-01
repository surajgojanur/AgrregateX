# Environment manifest (issue #67, Mac)

No credentials are recorded here. Raw preflight output is in `evidence/host-preflight.txt`, and checksums are in `evidence/checksums.txt`.

## R0 audit host (this PR, 2026-11-01T04:21Z)
| | |
|---|---|
| Host | Apple M1, 8 CPU, **8 GiB RAM**, macOS 27.2 arm64 |
| Swap at preflight | 7,168 MB total, **5,884 MB used** (memory-starved; see the stop rules in RUNBOOK) |
| Disk free | 15 GiB of 228 GiB |
| Docker | **Stopped** (Docker Desktop quit cleanly 08:59 IST; the operator chose not to relaunch it). VM was 3.8 GiB when running |
| Git | `main` @ `04f03b9` (`evidence/git-sha.txt`) |
| Python (offline tests) | 3.13, fastapi 0.162.0, psycopg 3; Node 22 / npm for the frontend |

## Recorded measurement environment (artifacts audited, not re-measured)
| | 1M / 10 tenants | 10M / 100 tenants |
|---|---|---|
| Artifact | `integration/scale/results/1m-10t-http/` | `integration/scale/results/10m-100t-http/`, `10m-100t-proof/` |
| PostgreSQL / pg_trickle | 18.6 (Debian 18.6-1.pgdg12+2, aarch64) / 0.108.3 | same |
| Image | `ghcr.io/trickle-labs/pg_trickle@sha256:94344bb98995b19c826f939739672481abaab8c25710e3910b48bdb7cf5b3b8d` (multi-arch index; arm64 child `e3490ecc…`) | same |
| API port (then) | 8095 | 8096 |
| Generator | `gen_synthetic.sql` sha256 `a4ec696e…deba6`, seed 42, Zipf s = 1, hash-per-order (deterministic) | same; 40 chunks, load 40.2 s |
| Data span | 90 UTC days, 2026-08-02 … 2026-10-30 (data end 2026-10-31T00:00Z) | same |
| Size | n/a | DB 5,674 MB; orders heap 1,116 MB + indexes 604 MB |
| Tenant skew (role tenants) | largest t1 = 340,560; median t6 = 56,965; smallest t10 = 34,091 | largest t1 = 1,930,247; median t51 = 37,901; smallest t100 = 19,471 |
| Client | serial urllib, monotonic clock, 3 warm-up + 50 measured per scenario | same |

## Not verified (blocks official qualification)
- The organizer generator, schema, version, seed, status/money/time semantics and skew manifest.
- Matched-run provenance between 1M and 10M (same container build, settings and background load). The evidence verifier classifies this as INSUFFICIENT EVIDENCE.
- Raw per-request samples (only per-scenario percentiles are stored).

## Approval record
| Phase | Approved? |
|---|---|
| R0 read-only audit, offline tests, docs | Allowed by #67 ("read-only audit/analysis and preparing scripts/docs are allowed now") |
| P1–P6 live phases | **Not approved.** Requested in the #67 comment / PR description |
