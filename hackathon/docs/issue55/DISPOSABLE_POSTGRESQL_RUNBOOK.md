# Issue #55 disposable PostgreSQL validation runbook

This runbook is preparation only. **Do not execute the database setup until a human explicitly approves this exact disposable target and the resource preflight passes.** It must never target the preserved demo or a teammate's environment.

## Proposed isolated target

- Compose project: `ax-issue55-raw-source-validation`
- PostgreSQL bind: `127.0.0.1:25655` only
- Optional API bind: `127.0.0.1:18155` only
- Fresh project-owned named volume: `ax_issue55_pgdata`
- PostgreSQL: 18.6 with the repository-pinned pg_trickle 0.108.3 image/digest
- DB resource limit: 1 GiB RAM, 1 CPU; API: 256 MiB, 1 CPU
- Fixture: no more than 100 rows; maximum run duration 10 minutes
- The API must use the restricted `ax_api` role. No superuser or `BYPASSRLS` for analytics requests.

No compose stack or image pull is started by this report. Before execution, verify the actual resolved image digest, architecture/platform support, ownership of the project/network/volume, and that ports 25655/18155 are unused. Bind every service to loopback. Do not use or attach to `round1-db`, ports 8093/8094/25560, or any existing volume.

## Mandatory approval and resource preflight

Approval must identify the disposable project, both ports, the fresh volume, the pinned image digest, resource limits, the maximum 100-row fixture, and the 10-minute duration. Approval to run offline tests is not approval for this live target.

Before starting, collect and retain:

```sh
date -u +%Y-%m-%dT%H:%M:%SZ
free -h
swapon --show
df -h
vmstat 1 5
ps -eo pid,comm,%cpu,%mem --sort=-%mem | head -20
ss -ltnp | rg ':(8093|8094|25560|25655|18155)\b' || true
docker ps --no-trunc
docker volume ls
docker network ls
```

Require at least **4 GiB available host RAM**, **5 GiB free persistent disk**, no sustained swap I/O, no competing benchmark, and no resource pressure likely to affect the existing demo. Abort if any condition fails or ownership is uncertain. Recheck the two proposed ports and exact project-owned volume/network immediately before start. Never use `docker compose down -v`; cleanup must name only the approved project resources and happen only after evidence is copied out and reviewed.

## Execution outline (after approval only)

Use a reviewed isolated compose definition with the exact approved project name, loopback binds, resource caps, pinned image digest, one CPU, and a new named volume. Run the existing schema/security setup and existing raw-source backend test suite; do not edit roles or policies to make tests pass. Use the application’s legitimate signed-cookie login for API tests. Verify `pg_trickle.enabled`, RLS policy flags, API role identity, extension versions, and session settings with read-only SQL before the fixture.

Run separately and preserve each result:

1. **Authentication:** unauthenticated 401, tenant user own-tenant success, cross-tenant 403, authorized admin behavior.
2. **Database isolation:** `ax_api` is not superuser and lacks `BYPASSRLS`; RLS is forced; transaction-local `ax.tenant_id` is set; a tenant-scoped read cannot see another tenant's source rows.
3. **Analytics:** summary, daily/hourly trends, top products, status/category breakdowns, `[from,to)` boundaries, partial buckets, empty ranges, and the tenant 2/product 116 cancelled-only shape. Independently compare API results to source SQL in the same requested interval.
4. **Failure behavior:** owner shard unavailable -> 503, limiter saturated -> 429, statement timeout -> bounded error, and no silent switch from raw source to rollup. No cross-shard fallback.
5. **Performance:** a small bounded GET-only request sample, with fixed concurrency, request count, errors/timeouts, p50/p95, dataset size, PostgreSQL/extension/image identity, CPU/RAM/disk, and statement timeout. Keep raw-source and rollup samples separate.

Do not perform live insert/update/cancellation, stream refresh/rebuild, load generation, fault injection, or G3 experiments under this runbook. Those need separate authorization and must not be inferred from these read-only checks.

## Evidence and stop conditions

Store sanitized request samples, SQL results, identity/version output, RLS checks, and resource observations under a new timestamped directory. Redact session cookies, passwords, DSNs, and private machine data. A mock or offline pass is not a live PostgreSQL pass. If any identity, isolation, resource, or provenance check is missing, report that category as **BLOCKED — NOT TESTED** or **INCONCLUSIVE**; do not claim Issue #55 is complete or G4 passed.

The full test matrix and current status are in [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md).
