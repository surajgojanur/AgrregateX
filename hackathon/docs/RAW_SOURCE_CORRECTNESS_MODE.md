# Raw-source correctness mode

## Why this mode exists

The Fedora demo and the Mac 1M synthetic run exposed an incorrect paid group in
`ax.st_day_product_status` after order status changes. The exact upstream
incremental-maintenance mechanism remains under investigation in Issue #50.
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

The four existing routes and their response data fields are retained. Responses
add `analytics_mode` and `provenance`. Raw-source provenance names `ax.orders`,
sets `uses_stream_tables` to false, and marks the result as a single SQL
statement snapshot. Existing `source` range fields remain present: raw mode has
no stream-table range and identifies the full requested source range. The
`freshness` field is null in raw mode because stream refresh age does not measure
source-query answers. Rollup mode continues to return the existing stream/raw
edge range and freshness metadata, with additive mode/provenance fields.

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
is not evidence of negative tenant isolation.

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
appropriate API restart, and end-to-end verification using a disposable or
otherwise approved target. It requires no migration, stream refresh, or rebuild.

The current React dashboard has a static explanatory caption describing complete
days as stream-table data and partial ranges as source data. This backend change
adds authoritative provenance to API responses, but does not make that caption
mode-aware. Do not activate the setting for dashboard use until the UI renders
the response's `analytics_mode`/`provenance` (or otherwise clearly identifies
raw-source results) and that UI change is reviewed. This task intentionally keeps
the frontend outside its change scope.

## Judge explanation

> We identified a correctness edge case in the upstream incremental
> maintenance engine. Instead of hiding the error, we built a reviewable
> alternative that derives answers directly from source data. It has different
> performance tradeoffs while the engine-level issue is investigated.

Do not claim this mode works on the live demo until an authorized runtime test
has confirmed it. The upstream defect and Issue #50 remain open; raw-source mode
does not make the rollup correct or close G4.

## Offline checks

From `hackathon/app`, install the test-only dependencies with
`python -m pip install -r requirements-test.txt`, then run
`python -m unittest discover -s tests -v`. These mocked tests do not start
PostgreSQL and do not qualify query performance or live RLS policy behavior.
