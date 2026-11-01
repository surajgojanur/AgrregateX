> FINAL REHEARSAL UPDATE — 2026-11-01, HEAD daefdd657339ca9e44805283108610a44ee50009: localhost8093 restored against preserved round1-db. HTTP verified, browser unavailable. Fresh oracle: product/day/status 0 missing, 1 extra; other two 0/0. Current correctness NOT READY. See FINAL_READINESS.md; this update supersedes historical availability/count/readiness statements below.

> Audit revision: `daefdd657339ca9e44805283108610a44ee50009`; 2026-11-01. Recorded evidence retains its own earlier provenance. Current localhost:8093 unavailable. No live feature certified ready.

# Eight terminal proofs

Run from repository root. All commands were checked against paths; HTTP health was executed and failed; summary availability is not verified now. Static evidence commands were inspected/read during audit. No credentials required. No SQL credentials projected.

## Proof 01: Revision — Screen 01

**Proves:** Revision, within stated scope.

```sh
git rev-parse HEAD
```

**Output:** Exact audit SHA above.

**SAY:** “No database capability is implied.”

**Can fail:** wrong checkout/path, service absent, authentication required, changed data. **Fallback:** open E1/E2/E3/E5 as appropriate, explicitly recorded; audit SHA in header is not the capture SHA. Spend at most five seconds. Do not print cookies or configuration.

## Proof 02: API availability — Screen 02

**Proves:** API availability, within stated scope.

```sh
curl --max-time 3 -sS http://127.0.0.1:8093/api/health
```

**Output:** Current audit: connection refused.

**SAY:** “This bounded probe determines whether to use recorded mode.”

**Can fail:** wrong checkout/path, service absent, authentication required, changed data. **Fallback:** open E1/E2/E3/E5 as appropriate, explicitly recorded; audit SHA in header is not the capture SHA. Spend at most five seconds. Do not print cookies or configuration.

## Proof 03: Summary route — Screen 02

**Proves:** Summary route, within stated scope.

```sh
curl --max-time 3 -sS http://127.0.0.1:8093/api/tenants/1/summary
```

**Output:** Current audit: unavailable; E1 recorded HTTP200.

**SAY:** “This is a PostgreSQL-backed endpoint, conditional on preflight.”

**Can fail:** wrong checkout/path, service absent, authentication required, changed data. **Fallback:** open E1/E2/E3/E5 as appropriate, explicitly recorded; audit SHA in header is not the capture SHA. Spend at most five seconds. Do not print cookies or configuration.

## Proof 04: Stream definitions — Screen 06

**Proves:** Stream definitions, within stated scope.

```sh
sed -n '1,160p' hackathon/sql/10_stream_tables.sql
```

**Output:** Actual SQL definitions, not live refresh state.

**SAY:** “Three maintained summaries serve different grouping grains.”

**Can fail:** wrong checkout/path, service absent, authentication required, changed data. **Fallback:** open E1/E2/E3/E5 as appropriate, explicitly recorded; audit SHA in header is not the capture SHA. Spend at most five seconds. Do not print cookies or configuration.

## Proof 05: Isolation source — Screen 04

**Proves:** Isolation source, within stated scope.

```sh
sed -n '1,90p' hackathon/sql/20_security.sql
```

**Output:** Forced RLS statements in source.

**SAY:** “Source establishes intended boundaries; runtime tests remain separate.”

**Can fail:** wrong checkout/path, service absent, authentication required, changed data. **Fallback:** open E1/E2/E3/E5 as appropriate, explicitly recorded; audit SHA in header is not the capture SHA. Spend at most five seconds. Do not print cookies or configuration.

## Proof 06: Oracle result — Screen 07

**Proves:** Oracle result, within stated scope.

```sh
cat hackathon/sharding/results/baseline-api-oracle.txt
```

**Output:** Recorded {"checks": 200, "mismatches": 0}.

**SAY:** “This independent recorded API comparison found no mismatch in its tested cases.”

**Can fail:** wrong checkout/path, service absent, authentication required, changed data. **Fallback:** open E1/E2/E3/E5 as appropriate, explicitly recorded; audit SHA in header is not the capture SHA. Spend at most five seconds. Do not print cookies or configuration.

## Proof 07: Rebuild/oracle evidence — Screen 07

**Proves:** Rebuild/oracle evidence, within stated scope.

```sh
tail -n 9 hackathon/app/tests/results/live-bonus-20261031T132216Z.txt
```

**Output:** Recorded oracle 0/0 and 17 passed/0 failed.

**SAY:** “This is a prior disposable-stack test, not a rebuild we run now.”

**Can fail:** wrong checkout/path, service absent, authentication required, changed data. **Fallback:** open E1/E2/E3/E5 as appropriate, explicitly recorded; audit SHA in header is not the capture SHA. Spend at most five seconds. Do not print cookies or configuration.

## Proof 08: Latency evidence — Screen 09

**Proves:** Latency evidence, within stated scope.

```sh
cat hackathon/sharding/results/measure-latency-lag.json
```

**Output:** Recorded latency and visibility samples.

**SAY:** “These numbers have bounded conditions and do not certify official scale.”

**Can fail:** wrong checkout/path, service absent, authentication required, changed data. **Fallback:** open E1/E2/E3/E5 as appropriate, explicitly recorded; audit SHA in header is not the capture SHA. Spend at most five seconds. Do not print cookies or configuration.

