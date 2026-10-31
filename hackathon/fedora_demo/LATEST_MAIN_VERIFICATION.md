# Latest Main Fedora Demo Verification

Date: 2026-11-01 (Asia/Kolkata)

## 1. Final status

**PARTIAL — the latest-main analytics demo is running and verified against the preserved database. Monitoring correctly remains degraded because the existing `ax_monitor` login cannot read `pgtrickle.pgt_dependencies`. Migration 003 was not applied.**

Open the latest-main demo at **http://127.0.0.1:8094/**. The separate process on `127.0.0.1:8093` was left untouched.

## 2. Repository verification

- Fetched `origin`; latest `origin/main` at verification time: `2cc3a757cee37efc75586780df56fbefd2737e94`.
- Isolated worktree: `/home/god/Documents/github/AgrregateX-final-demo`.
- Branch: `fix/fedora-final-demo-verification`, based on latest `origin/main`.
- Original checkout and its untracked files were preserved; the worktree list and Issue #12 coordination rules were checked before work.
- No application source files were changed. This report and runtime evidence originated as untracked task artifacts in the isolated worktree; the published subset is staged separately after review.

## 3. System status

- Fedora 44.
- 4 CPUs; disk had 228 GiB available at inspection. RAM: 7.5 GiB total, 1.6 GiB available; swap: 7.5 GiB total, 1.4 GiB available. Memory was constrained, so no extra database or benchmark stack was started.
- Reused running `round1-db` at loopback port 25560. It reported PostgreSQL 18.6, database `aggregatex`, pg_trickle `0.108.3`.
- `ax` schema, `orders`, `products`, and all three expected stream tables were present. Read-only tenant counts showed 1,002 orders including 1,000 seeded orders.
- The configured `ax_api` login completed a tenant-scoped read-only query for tenant 1.
- Latest-main backend: Uvicorn, bound only to `127.0.0.1:8094`; `/api/health` returned HTTP 200 at final check. Raw log and PID file are retained locally and excluded from publication.
- Local demo configuration used `AX_AUTH_DISABLED=1` and `AX_ENABLE_DEMO_WRITES=0`, and connected to the existing DB. DB login values were inherited from the existing local API service without printing them.
- Port 8093 had a different pre-existing process. It was not stopped or modified. Port 8094 serves the current isolated latest-main build.

## 4. Application verification

| Feature | Status | Evidence |
|---|---|---|
| Landing | PASS | HTTP 200, expected AgrregateX heading/branding and OPEN DASHBOARD navigation; desktop and mobile screenshots |
| Dashboard | PASS | Current UI rendered database-backed tenant KPI and chart panels |
| Analytics APIs | PASS | Smoke test: all 12 checks passed; explicit GET sweep including hourly trends also returned 200 JSON |
| Tenant selection | PASS | Changed from tenant 1 to tenant 2 in browser; tenant-specific summary API values differ |
| Charts | PASS | Dashboard chart panels rendered; daily and hourly trends endpoints returned valid data |
| Shards | PASS | API/UI report the actual single `default` shard; metadata complete, 1,002 orders / 1,000 seed orders |
| Engine | PASS | Three expected stream tables visible; status ACTIVE and configured refresh mode DIFFERENTIAL; runtime effective mode reported as NO_DATA where applicable |
| Monitoring | PARTIAL | Page renders. Direct health invocation as `ax_monitor` returns permission denied on `pgt_dependencies`; monitoring stays UNKNOWN/degraded. No privilege change or migration was run. |
| Mobile responsiveness | PASS | 390 px viewport: no document-level horizontal overflow; key pages rendered |
| Theme toggle | PASS | Browser clicked both dark→light and light→dark controls successfully |
| Time range controls | PASS | 24 h, 7 d, 30 d, 90 d presets selected; hourly grain selected for 24 h |
| Browser console | PASS | No page errors or console errors recorded in browser run |
| Reload/routing | PASS | Dashboard reload and landing-to-dashboard route worked |

Representative cross-check: tenant 1 dashboard summary returned 138 orders and 17,191,579 sales cents. An independent read-only SQL query under `ax_api` with tenant scope 1 returned the same 138 orders and 17,191,579 sales cents. The API's 304 sold units intentionally excludes non-sale statuses; raw all-status units were 413.

The frontend assets were rebuilt from this worktree's current source, so this URL is based on the fetched latest main revision rather than the process on port 8093.

## 5. Automated test results

- Frontend lint: `npm run lint` — PASS.
- Frontend unit tests: `npm test` — 3 passed, 0 failed.
- Frontend production build: `npm run build` — PASS (Vite produced the current `dist` assets).
- Backend: `PYTHONPATH=hackathon/app /tmp/ax-issue34-venv-current/bin/python -m unittest discover -s hackathon/app/tests -v` — 36 passed, 0 failed, 1.819 s.
- Fedora demo helper tests: `python3 -m unittest discover -s hackathon/fedora_demo -p 'test_*.py' -v` — 9 passed, 0 failed, 2.021 s.
- Live smoke: `python3 hackathon/fedora_demo/smoke.py --base-url http://127.0.0.1:8094 --tenant-id 1` — 12/12 GET checks passed.
- Browser run: 21 stricter desktop/mobile checks passed, including content-ready screenshots for all five pages at both viewport sizes, range/grain and theme controls, navigation, reload, and overflow. No browser errors. No live write tests were run.

The Python environment was reused from `/tmp` and `httpx2` was installed there because the initial backend test attempt showed that the TestClient dependency was absent. No repository dependency files were changed. Npm reported six moderate dependency advisories during `npm ci`; no dependency upgrade was attempted during the demo restore.

## 6. Bugs fixed

No application source bug required a code change. The integration issue was that port 8093 was occupied by a pre-existing older application process, so starting the latest-main build there would have displaced it. The current-main build is available on loopback port 8094 instead. The frontend was rebuilt from current source and the backend launched against the verified existing database with writes disabled.

## 7. Remaining problems

- **Demo-breaking:** none found for the analytics flow verified here.
- **Noncritical:** Monitoring remains degraded because `ax_monitor` health diagnostics fail with SQLSTATE 42501 on `pgtrickle.pgt_dependencies`. This accurately remains visible. Migration 003 from the monitoring work has not been applied.
- **Environment:** system memory and swap usage are elevated. Do not add a database stack or large benchmark during the demo.
- **Staleness:** the engine data is visible, but this run did not independently establish whether any historical `stale=true` condition represents a current scheduler delay. No refresh or scheduler action was taken.
- **Performance targets:** no 1M/10M dataset or throughput benchmark was run.
- **Teammate-owned work:** no Issue #42 / Mac two-shard work was changed; this Fedora environment reports its actual one-shard topology.

## 8. Evidence and reproduction

Evidence generated by this run is under `hackathon/fedora_demo/evidence-20261101/`. The screenshots and sanitized JSON results are the portable evidence subset. The raw API log and PID file are local-only and excluded from publication.

- `desktop-dark-landing.png`, `desktop-dark-dashboard.png`, `desktop-dark-engine.png`, `desktop-dark-shards.png`, `desktop-dark-monitoring.png`
- `mobile-light-landing.png`, `mobile-light-dashboard.png`, `mobile-light-engine.png`, `mobile-light-shards.png`, `mobile-light-monitoring.png`
- `browser-results.json`, `smoke.json`

Recheck API smoke from repository root with:

```bash
python3 hackathon/fedora_demo/smoke.py --base-url http://127.0.0.1:8094 --tenant-id 1
```

At capture time, the latest-main backend was running on loopback port 8094. Its local PID file can identify the process on the Fedora host if needed; it is deliberately not part of the published evidence.

## 9. Judge-readiness verdict

- Website running: **Yes**, at http://127.0.0.1:8094/ on this Fedora host.
- Based on latest main: **Yes**, `2cc3a757cee37efc75586780df56fbefd2737e94`.
- Four analytics families functional: **Yes** — daily trends, hourly trends, top products, and status/category breakdowns returned real API data.
- Connected to PostgreSQL: **Yes**, existing `aggregatex` database through the configured application login.
- Demo database preserved: **Yes** — read-only checks and GET requests only; no writes, migrations, role or RLS changes, reseeding, container restarts, or volume operations.
- Desktop and mobile: **Yes** for the tested 1440 px and 390 px viewports.
- Safe to demonstrate: **Yes** for the verified read-only analytics demo on this machine. Monitoring will visibly show the known degraded state; explain that the monitoring permission repair is pending review. Keep the application on loopback and demo writes disabled.
- Next priority: human review and separately authorized validation of the complete monitoring permission repair; then investigate any current stale stream status in read-only diagnostics.
