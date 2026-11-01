> FINAL REHEARSAL UPDATE — 2026-11-01, HEAD daefdd657339ca9e44805283108610a44ee50009: localhost8093 restored against preserved round1-db. HTTP verified, browser unavailable. Fresh oracle: product/day/status 0 missing, 1 extra; other two 0/0. Current correctness NOT READY. See FINAL_READINESS.md; this update supersedes historical availability/count/readiness statements below.

> Audit revision: `daefdd657339ca9e44805283108610a44ee50009`; 2026-11-01. Recorded evidence retains its own earlier provenance. Current localhost:8093 unavailable. No live feature certified ready.

# Preflight and rehearsal

Current readiness: PARTIAL package; all live screens NOT READY — USE FALLBACK. E1 screenshots and E2–E7 recorded evidence READY WITH RECORDED EVIDENCE. Best documented product environment: Fedora single-shard recording. No verified current live machine; Mac evidence is separate.

- [ ] Confirm exact revision with git rev-parse HEAD; preserve dirty/untracked files. Do not expose secrets.
- [ ] On a fresh checkout verify recorded files and screenshots exist offline; do not start provisioning automatically.
- [ ] Human identifies intended machine, database, role and port without projecting credentials. Historical Fedora URL is http://127.0.0.1:8093; DB loopback25560/aggregatex is historical, not current certification.
- [ ] Run bounded health GET; successful liveness alone does not certify monitoring/correctness.
- [ ] Rehearse actual dashboard date boundaries on populated data; tenant1→2; all four families; no writes.
- [ ] If secure mode is available, separately verify own-tenant access and cross-tenant403 with test credentials kept off projection. Operator bypass is not proof. No current signoff.
- [ ] Verify physical shards independently if claiming live two-shard; otherwise use E4 recorded only. Do not partition.
- [ ] Authorized read-only SQL must use intended role, READ ONLY transaction and short timeout; no held003 scripts. Compare current counts without assuming E1 unchanged.
- [ ] Verify settled oracle in an approved disposable rehearsal before current correctness claims; do not execute expensive full scans on preserved stack merely for judging.
- [ ] Verify monitoring actual state, effective refresh mode/history and warnings. Keep degraded visible.
- [ ] Copy evidence bundle, benchmark files and PNGs offline; open tabs in screen order.
- [ ] 22–26pt terminal; hide history, notifications, private tabs; 1440×900 or readable projector resolution.
- [ ] Charge both laptops; power adapter, display cable; one-display fallback ready.
- [ ] Stopwatch rehearsal: 600s including clicks. Other member silently operates. Five-second failure cutoff.
- [ ] Rehearse 300s and120s versions; identify sentences to cut before stage.

Signoff table: record timestamp, actual machine, HEAD, auth mode, data size, evidence path, pass/fail per screen. Only mark READY after observing that screen in the exact presentation environment. No destructive recovery. Original PRD images and remote PR/issue review remain human follow-ups; gh was unavailable here.
