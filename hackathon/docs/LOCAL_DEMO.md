# Login-free local presentation

Stacks on PR #25 (including #24), integrating #23; no PR merged into main.

Build: `cd hackathon/frontend && npm ci && npm run build`. Activate Python with app requirements installed. Set AX_DB_HOST, AX_DB_PORT, AX_DB_NAME and database role passwords for your initialized demo. Run `bash hackathon/app/run_local_demo.sh`.

Open http://127.0.0.1:8093/ then OPEN DASHBOARD. Monitoring: /app#/monitoring. Old /login and /register redirect to /. The launcher explicitly sets AX_AUTH_DISABLED=1, uses the built-in operator, binds only 127.0.0.1, disables writes and starts no databases. All local visitors get operator access. Never use bypass on a shared/public deployment. No credentials in React. Backend default stays AX_AUTH_DISABLED=0; signed-cookie auth and RLS remain. Secure mode without a session shows restricted access, with no redirect loop.

B1 freshness, B2 rebuild CLI and B3 limits are retained. Monitoring follows operator authorization and shows query-limit counters. Metrics are bounded/process-local and reset on restart; CDC backlog is estimated. A single configured DB appears as default, not invented A/B shards.

## Fedora verification

Frontend ESLint PASS, frontend tests 3/3 PASS, production build PASS (256 MiB Node heap). Backend unit/mock tests 21/21 PASS, including B1/B2/B3 and secure monitoring 401/403. `just fmt` and `just lint` unavailable: just is not installed; no Rust build attempted.

Chromium actually rendered and screenshots were inspected: landing CTA to dashboard, all four routes and reloads, old auth redirects, mobile dashboard with no document overflow, no page runtime errors. Screenshots are local in /tmp/ax-navigation-evidence/{landing,dashboard,mobile-dashboard,monitoring}.png.

Live read-only checks against existing round1-db: analytics endpoints, B1 freshness, engine, monitoring and limits 200. Shards page shows Internal error: existing database lacks ax.tenant_order_counts(), independently verified with to_regprocedure returning NULL. Requires compatible disposable schema; no existing database was migrated. No two-shard availability claim. B2 rebuild was not rerun against an existing DB.
