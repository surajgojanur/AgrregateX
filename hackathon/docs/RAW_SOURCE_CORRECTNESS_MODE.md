# Raw-source correctness mode

## Why this mode exists

The Fedora demo and the Mac 1M synthetic run exposed an incorrect paid group in
`ax.st_day_product_status` after order status changes. The approved controlled Mac reproduction now **observes** the negative `D(paid)`
CDC event disappearing between the raw buffer and the final post-stage relation
([#50](https://github.com/surajgojanur/AgrregateX/issues/50), completed as a diagnosis).
The narrower reducer-versus-visibility boundary and the multi-row Mac paid-only
variant remain unresolved; upstream correction is tracked by [#54](https://github.com/surajgojanur/AgrregateX/issues/54).
This optional application mode calculates each analytics answer from current
`ax.orders` rows (and the tenant-matched `ax.products` rows for product and
category labels), avoiding the three pg_trickle stream tables for those answers.
It does not repair, refresh, rebuild, or otherwise change the stream tables.

## Configuration and behavior

Set `AX_ANALYTICS_READ_MODE=raw_source` in the API process to select this mode.
The only accepted values are `rollup` and `raw_source`; unset/empty defaults to
`rollup` to preserve existing deployments. An invalid value prevents the API
from starting with a clear configuration error. The selector is server-side;
request parameters cannot choose or override it.

The four existing routes and their response data fields are retained. Each
response adds `analytics_mode` and `provenance`, including the source table list,
whether stream tables were used, and `consistency_scope:
per_http_response_only`. Each endpoint runs one SQL statement, but the four
independent requests do not share a PostgreSQL snapshot. Raw-source provenance
names the tables actually read, sets `uses_stream_tables` to false, and marks
the full requested source range. The `freshness` field is null in raw mode
because stream refresh age does not measure source-query answers. Rollup mode
continues to return its stream/raw edge ranges and refresh metadata.

The dashboard now derives a source indicator from all four responses. It shows
**Direct source queries** only when all four responses agree and report valid
raw-source provenance; it shows **Incremental rollups** only when all four
responses agree on rollup provenance. Mixed, missing, malformed, or
contradictory metadata is shown as mixed or **Data source not verified**, with
per-panel details. The mode is never selected by a browser setting. Query
round-trip time is reported separately from database freshness.

Raw queries retain the existing [from,to) UTC semantics, sale definition
(`status NOT IN ('cancelled','refunded')`), integer-cent money, hourly range
limit, product limit (1–50), response fields, and deterministic product ranking
(sales descending, product ID ascending). Every analytics family executes one
source SQL statement, so each answer is internally consistent at that
statement's PostgreSQL snapshot. Separate HTTP endpoints do not share a
cross-request snapshot.

## Security boundaries

The existing dependency chain remains in place: `auth.current_user` verifies
the signed `ax_session`; `auth.authorize_tenant` runs before shard routing;
`db.shard_for` chooses the directory's owning shard; and `_run` retains the
per-tenant concurrency slot and calls `db.tenant_tx("api", tenant_id)`. That
transaction uses the restricted `ax_api` pool and sets `ax.tenant_id` with
transaction-local `set_config`. Queries additionally bind tenant and time
parameters. Product/category joins match both tenant ID and product ID.

No superuser, BYPASSRLS, security-definer query helper, cross-shard fallback,
role/policy/grant change, or RLS bypass is added. Existing shard outage behavior
remains fail-closed with HTTP 503. A database timeout follows the existing
bounded shard-query error path; raw mode never silently falls back to a known
incorrect rollup.

The source SQL is one statement per response, so PostgreSQL uses one statement
snapshot for that response. This does not provide a shared snapshot across
separate HTTP requests. RLS remains a database authorization boundary; the
application's tenant check and transaction-local tenant setting are retained.
See the [PostgreSQL 18 row security documentation](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)
and [transaction isolation documentation](https://www.postgresql.org/docs/18/transaction-iso.html).

Tests of legitimate signed sessions and forced-RLS behavior do not establish
security claims from the localhost operator-bypass demonstration. The bypass
is not evidence of negative tenant isolation. Issue #55's offline UI tests do
not replace the pending live authentication/RLS validation on a separately
approved disposable PostgreSQL target.

## Performance and deployment limitations

Raw queries scan the requested tenant/time slice of source orders and may be
substantially slower than maintained rollups at 1M or 10M orders. No raw-mode
latency or database-safety performance result is claimed. The existing
statement timeout, pool/connect bounds, tenant concurrency limiter, and hourly
range limit remain active; an over-budget query fails rather than returning a
partial result. Do not compare raw-source latency with rollup latency as if they
were the same execution path.

This change is code for review only and is not enabled on the running Fedora
service. Activation requires a reviewed deployment configuration change, an
appropriate API/frontend rollout, and end-to-end verification using a
disposable or otherwise approved target. It requires no migration, stream
refresh, or rebuild. Roll back by restoring/unsetting
`AX_ANALYTICS_READ_MODE=rollup`, then redeploying/restarting the API and
frontend together; verify all four endpoints report rollup mode and the UI
labels the results accordingly. Do not switch modes in production without
checking query timeouts and the resulting source-query load.

The dashboard freshness chip reports only the last completed stream refresh
when all four analytics responses are verified rollups. It explicitly says
that refresh age does not establish commit-to-visible delay or correctness. In
raw-source mode, the chip describes the source rows visible to each SQL
statement and may show when the browser received the summary response. The
separate engine-health panel remains visible but is labeled as engine status,
not direct-source answer freshness; malformed/null engine fields are rendered
as unavailable.

Dashboard requests are independently tracked by tenant, time interval, grain,
and breakdown. A tenant/filter change aborts superseded requests and hides the
previous query's values immediately. Same-query auto-refresh does not overlap;
each panel has its own loading, error, latency, result, and provenance state.
Partial failures do not keep the failed panel's old values on screen. An
unavailable shard remains unavailable; there is no raw/rollup fallback.

## Activation and verification checklist

1. Review the code and deployment configuration; keep `rollup` as the default.
2. On an explicitly approved disposable target, run signed-cookie, cross-tenant,
   forced-RLS, tenant-routing, timeout, 503/429, and analytics-oracle checks.
3. Verify all four responses' mode, source tables, ranges, statement-snapshot
   scope, and freshness fields against the executed SQL.
4. Compare the cancelled-only incident fixture directly with source SQL and
   confirm product 116 is absent from paid Top-N.
5. Measure raw-source performance separately from rollup performance and record
   dataset size, host resources, sample counts, timeouts, and percentiles.
6. Confirm the UI shows one uniform mode only when all four valid responses
   agree; exercise mixed/error states and tenant/filter changes.
7. Keep Issue #31/G4 marked FAIL until the maintained stream-table defect is
   independently corrected and validated. Raw-source mode does not pass G4.
8. For rollback, restore `rollup`, restart/redeploy the API and frontend, then
   verify the rollup provenance and UI indicator.

The Issue #55 implementation and current validation limits are summarized in
[`issue55/VALIDATION_REPORT.md`](issue55/VALIDATION_REPORT.md). The exact live
test gate is in [`issue55/DISPOSABLE_POSTGRESQL_RUNBOOK.md`](issue55/DISPOSABLE_POSTGRESQL_RUNBOOK.md).

## Judge explanation

> We identified a correctness edge case in the upstream incremental
> maintenance engine. Instead of hiding the error, we built a reviewable
> alternative that derives answers directly from source data. It has different
> performance tradeoffs while the engine-level issue is investigated.

Do not claim this mode works on the live demo until an authorized runtime test
has confirmed it. The upstream **correctness failure remains**; [#50](https://github.com/surajgojanur/AgrregateX/issues/50)
is closed for the completed diagnostic only, while fix/acceptance issues [#54](https://github.com/surajgojanur/AgrregateX/issues/54)
and [#31](https://github.com/surajgojanur/AgrregateX/issues/31) stay open. Raw-source mode does not repair the maintained rollup or close G4.

## Offline checks

From `hackathon/app`, install the test-only dependencies with
`python -m pip install -r requirements-test.txt`, then run
`python -m unittest discover -s tests -v`. These mocked tests do not start
PostgreSQL and do not qualify query performance or live RLS policy behavior.
