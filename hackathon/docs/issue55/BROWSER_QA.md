# Issue #55 mock API browser QA

**Scope:** Local Vite frontend with deterministic Playwright route mocks. No API server, PostgreSQL instance, preserved demo port, or write endpoint was contacted.

## Results

- Chromium via `/usr/bin/google-chrome`, Playwright already installed on the host.
- Viewports: 1440, 1024, and 390 CSS pixels. Each had document `scrollWidth == clientWidth` and rendered all five `.ax-panel` regions (four analytics panels plus the engine-health panel).
- Exercised raw-source status breakdown, mixed response modes, uniform rollup metadata, unknown mode, malformed top-products collection, owning-shard 503, reload, and the accessible theme toggle in both directions.
- No uncaught page exceptions. The mock 503 generated the expected browser resource error. Aborted freshness requests during page cleanup were also observed and are expected cancellation behavior.
- The test harness fulfilled only `/api/**` requests locally; it did not submit writes.

## Captures

- [`1440 desktop`](browser-qa/ax-issue55-1440.png)
- [`1024 tablet`](browser-qa/ax-issue55-1024.png)
- [`390 mobile`](browser-qa/ax-issue55-390.png)
- [`mixed provenance`](browser-qa/ax-issue55-mixed.png)
- [`rollup mode`](browser-qa/ax-issue55-rollup.png)
- [`owning shard unavailable`](browser-qa/ax-issue55-503.png)
- [`light theme`](browser-qa/ax-issue55-light-1440.png)
- [`dark theme`](browser-qa/ax-issue55-dark-1440.png)

These are local mocked-browser evidence only. They do not prove live authentication, database SQL behavior, RLS, or production deployment.
