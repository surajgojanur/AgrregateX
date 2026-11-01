# Issue #55 validation report

**Status: PARTIAL — offline implementation validated; live PostgreSQL/RLS tests BLOCKED — NOT TESTED.**

## Repository and scope

- Main base verified at start of this work: `4bddde77f3c9f55d45945ce35e40a94e331399c8`.
- Work branch: `feat/issue55-mode-aware-dashboard`.
- Scope: mode-aware dashboard provenance, per-panel request state, freshness wording, API snapshot-scope metadata, offline tests, and documentation.
- No upstream Rust code, migrations, G3 scripts, scale fixtures, or teammate-owned evidence changed.

## Changed files

- `hackathon/frontend/src/pages/Dashboard.jsx` — per-response source labels, query-state handling, freshness wording, and stale-request protection.
- `hackathon/frontend/src/pages/dashboard.css` — compact theme-token indicator, badges, panel warning/error styles, and narrow viewport layout.
- `hackathon/frontend/src/components/analytics/AnalyticsProvenance.jsx` — accessible source/freshness UI components.
- `hackathon/frontend/src/lib/analyticsProvenance.js` — strict response metadata, source-range, and four-panel classification helpers.
- `hackathon/frontend/src/lib/dashboardRequestGate.js` and `dashboardState.js` — abort/generation gate, independent panel result states, and fail-closed validation for required summary fields and malformed collection rows.
- `hackathon/frontend/scripts/tests/analytics-provenance*.test.mjs` and `dashboard-state.test.mjs` — classification, state, and rendered accessibility tests.
- `hackathon/app/axapi/main.py` — explicit per-response consistency scope in API provenance.
- `hackathon/app/tests/test_raw_source_mode.py` — raw and rollup metadata assertions.
- `hackathon/docs/RAW_SOURCE_CORRECTNESS_MODE.md` — refreshed mode, freshness, activation, rollback, and verification guidance.
- `hackathon/docs/issue55/VALIDATION_REPORT.md` and `DISPOSABLE_POSTGRESQL_RUNBOOK.md` — evidence and approval-gated live test instructions.
- `hackathon/docs/issue55/BROWSER_QA.md` and `browser-qa/*.png` — local mock API screenshots and browser results.

## Implemented behavior

- The dashboard reads mode and provenance only from each API response. It displays **Direct source queries** or **Incremental rollups** only when all four responses have valid matching provenance.
- Missing/unknown metadata is **Data source not verified**. Conflicting or incomplete results show a mixed-source alert and per-panel labels.
- The old static stream-table caption was removed. Raw-source copy identifies authoritative source rows and independent statement snapshots; rollup copy explains complete UTC buckets and source-query edges without equating refresh recency with correctness.
- Raw-source answers do not use stream freshness. The independent engine-health panel is explicitly separated from answer freshness. Null and malformed age/table fields are guarded.
- Dashboard requests are keyed to tenant, date range, grain, and breakdown. Tenant/filter changes hide prior-query values immediately, abort prior requests, and ignore late completions. Same-query auto-refresh is bounded to one in-flight set. A failed panel does not retain its previous result; other panels report their own status and provenance.
- The API now labels its snapshot contract `consistency_scope: per_http_response_only`; this does not claim one shared snapshot across four HTTP requests.
- The classifier requires all four panels to have succeeded and have verified source metadata. Provenance verification also matches the response tenant ID, trend grain, and breakdown selector against the current dashboard request. A failed panel is labeled unavailable even when its source metadata is otherwise valid.
- The Live mutation panel now calls its result a scoped touched-group visibility sample and explicitly says that a match does not resolve the G4 defect.

## Offline validation performed

From `hackathon/frontend`:

- `npm ci` — completed; 156 packages installed. npm reported 6 moderate dependency audit findings; dependencies were not upgraded.
- `npm test` — **24/24 passed**, including the malformed-summary/valid-provenance regression, malformed chart/table rows, contradictory tenant metadata, request selector mismatches, stale request handling, partial 503s, and server-rendered accessibility labels.
- `npm run lint` — passed with zero warnings/errors.
- `npm run build` — passed (Vite production build).
- From `hackathon/app`, `/tmp/ax-raw-source-venv/bin/python -m unittest discover -s tests -v` — **55/55 passed**, including mocked raw-source route selection, signed auth/tenant checks, API-mode override rejection, restricted tenant transaction setup, unavailable-shard behavior, and rollup response compatibility.

Mocked interactive Chromium QA was run against a local-only Vite server using deterministic `/api/**` route fixtures. Results and screenshots are recorded in [`BROWSER_QA.md`](BROWSER_QA.md). All tested viewports had no horizontal overflow; raw, rollup, mixed, unknown, malformed-panel, 503, reload and light-theme scenarios rendered without uncaught page exceptions. The expected mock 503 console error was observed. The browser never contacted the preserved demo.

The new malformed-summary regression was run before the classifier fix and failed as expected: classifyAnalyticsSet returned uniform for three successful raw panels plus an error panel whose provenance was verified. It passes after requiring every panel to have succeeded.

These backend tests use mocks and do not start PostgreSQL. No live database-backed test was run.

## PostgreSQL, auth, and RLS status

**BLOCKED — NOT TESTED.** There was no separately approved disposable database target. Read-only host observations showed approximately 1.5 GiB available RAM and 6.3 GiB swap in use, below the required live-test headroom; no database/container was started. The preserved 8093/8094 services and `round1-db:25560` were not accessed for analytics, modified, or restarted during this work. No writes, refreshes, migrations, role changes, or RLS changes were performed.

Offline mocks do not prove signed-cookie authentication, cross-tenant denial, forced RLS, restricted-role behavior, shard isolation, query timeout behavior, or PostgreSQL SQL compatibility. The operator-auth bypass is not evidence for tenant isolation.

## GitHub CI provisioning failure

Inspected PR #59's CI run [41256340026](https://github.com/surajgojanur/AgrregateX/actions/runs/41256340026). Both **Unit tests (PR gate, linux-amd64)** and **Integration tests** failed in the Setup pgrx environment step; their Rust test and integration steps were skipped. The exact failing command was the HTTPS fetch of the PGDG signing key and its log reports **curl: (56) Failure when receiving data from the peer**. A narrow bounded-retry improvement and detailed diagnosis are being delivered separately in the CI reliability PR; this does not establish that a later hosted run passes.

The shared setup step identifies the failing command directly. This is a provisioning/network failure, not a failed test assertion. Other independent checks (secret scanning, release evidence, upgrade completeness, and monitoring contract) succeeded; the aggregate PR correctness check failed transitively because the required jobs did not pass. No CI rerun was manually launched or represented as green.

## Correctness and known issue

The application raw-source mode is an alternative query path; it does not repair the maintained stream tables. The G4 stream-table correctness verdict remains **FAIL** under Issue #31 until the upstream maintenance defect is corrected and independently validated under Issue #54. Raw-source mode has not been verified against a live PostgreSQL 18.6 / pg_trickle 0.108.3 runtime in this work.

## Next safe action

Run the isolated signed-session/RLS and source-oracle matrix in [`DISPOSABLE_POSTGRESQL_RUNBOOK.md`](DISPOSABLE_POSTGRESQL_RUNBOOK.md) only after explicit approval for that exact target and a successful resource preflight. Then perform mocked interactive browser QA in a separate local-only harness; do not point it at the write-enabled demo.
