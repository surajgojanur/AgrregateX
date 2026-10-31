# AgrregateX API + dashboard

FastAPI read layer over the pg_trickle stream tables in ENGINE_CONTRACT v1
(`../docs/handoffs/opus.md`). It also serves the built React UI (`../frontend`), so the whole demo runs on one port.

```bash
cd hackathon
docker compose up -d --build        # db (seeded 100k REPRESENTATIVE orders) + writer (5 changes/s) + api/ui
open http://127.0.0.1:8090/login     # tenant2@demo.local / demo1234  ·  admin@demo.local / demo1234
docker compose down -v               # stop and delete the demo data
```

The default credentials in `compose.yaml` are **local demo values**. Override them through the environment (for example
`AX_DEMO_PASSWORD`, `AX_*_PASSWORD`, `AX_SESSION_SECRET`) for anything that is shared.

Dev loop for the UI: keep the stack running, then `cd frontend && npm run dev`. Vite proxies `/api` to `127.0.0.1:8090`.

## Endpoints (`/api/docs` has the OpenAPI)
| | |
|---|---|
| `POST /api/auth/login` · `GET /api/auth/me` · `POST /api/auth/logout` | demo users: `tenant<N>@demo.local` gets tenant N only; `admin@demo.local` is the operator |
| `GET /api/health` | API, database and pg_trickle version |
| `GET /api/tenants` | the tenants this session may read |
| `GET /api/tenants/{id}/summary?from&to` | sales, orders, units, average order, cancel rate, per-status totals |
| `GET /api/tenants/{id}/trends?from&to&grain=day\|hour` | time series (hourly limited to 31 days) |
| `GET /api/tenants/{id}/top-products?from&to&limit=10` | exact Top-N for any range; ties broken by `product_id` |
| `GET /api/tenants/{id}/breakdown?from&to&by=category\|status` | |
| `GET /api/tenants/{id}/freshness` | per stream table: last completed refresh (handoff F6) |
| `POST /api/tenants/{id}/live-write` `{action: insert\|cancel, order_id?}` | commits a real change and reports the measured commit→visible time per stream table, using the pg_trickle frontier LSN (`AX_ENABLE_DEMO_WRITES=1`) |
| `GET /api/engine` | operator only: stream-table modes, refresh stats, recent refreshes, CDC buffers, health checks, settings |

## Isolation, defense in depth
1. **API layer:** the tenant in the URL must be the session's tenant (operators excepted). Otherwise the API returns 403, and it gives the same answer for tenants that don't exist.
2. **Database layer:** every query runs as `ax_api` (or `ax_writer`) inside a transaction with `set_config('ax.tenant_id', …, true)`. FORCE RLS on the stream tables and on `orders`/`products` limits rows to that tenant. A missing setting returns zero rows.
3. **Monitoring** uses a separate `ax_monitor` role with no access to tenant fact rows.

## Exact windows
Complete UTC days or hours come from stream tables. Partial edges come from raw `ax.orders` through the `(tenant_id, created_at)` index.
Every response states which ranges came from which source (`source`).

## Verified (2026-10-31, M1 laptop, 100k REPRESENTATIVE orders, n=1)
- `tests/api_oracle.py`: **180/180** API answers equal a direct SQL recomputation from raw orders. That covers summary, Top-10, category and day/hour trends, for 3 tenants × 12 windows (including a 2-second window across midnight), with the writer paused.
- HTTP security matrix: wrong password → 401; cross-tenant read → 403; tenant reading `/api/engine` → 403; forged cookie → 401; cross-tenant cancel → 404 with the row unchanged (RLS); bad timestamp → 422.
- Live write over HTTP: insert visible in all three stream tables in 1.94 s; cancel in 2.05 s (DIFFERENTIAL 1s, writer at 5 changes/s).

## Known limits
- Demo login only (shared demo password, no user store).
- Single shared-DB topology.
- **Write rate is limited by upstream finding F3/PROPOSAL P1.** Raising `AX_WRITER_RATE` far above about 50/s makes refresh fall behind.
- Not the PRD benchmark harness (G-1..G-5); that stays with Codex.

## Sharded mode (issue #19)
Set `AX_SHARDS="a=host:port,b=host:port"` and `AX_SHARD_DIRECTORY=<directory.json>`. The API then routes each tenant to its
owning shard and returns **503** (no cross-shard fallback) when that shard is unreachable. The demo stack is
`compose.sharded.yaml` (port 8091). Design, failure semantics, runbook and measured results:
`../docs/handoffs/opus-sharding.md`.
