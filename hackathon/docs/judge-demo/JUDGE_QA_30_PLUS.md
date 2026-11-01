> FINAL REHEARSAL UPDATE — 2026-11-01, HEAD daefdd657339ca9e44805283108610a44ee50009: localhost8093 restored against preserved round1-db. HTTP verified, browser unavailable. Fresh oracle: product/day/status 0 missing, 1 extra; other two 0/0. Current correctness NOT READY. See FINAL_READINESS.md; this update supersedes historical availability/count/readiness statements below.

> Audit revision: `daefdd657339ca9e44805283108610a44ee50009`; 2026-11-01. Recorded evidence retains its own earlier provenance. Current localhost:8093 unavailable. No live feature certified ready.

# Judge questions ranked by likelihood and risk

First six are highest risk; remaining questions are likely technical follow-ups. All answers refer to bounded evidence, not a new live test.

## 1. Did you build the engine?

**Risk:** HIGH. **Likelihood:** HIGH.

**SHORT ANSWER:** No. pg_trickle is upstream; we built the tenant-aware application and verification tooling.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 2. Can you handle ten million orders?

**Risk:** HIGH. **Likelihood:** HIGH.

**SHORT ANSWER:** We have not completed the official ten-million-row run. The current evidence supports a small prototype.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E1/E6 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E1/E6; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 3. Why did OLTP get worse?

**Risk:** HIGH. **Likelihood:** HIGH.

**SHORT ANSWER:** Capture and refresh consume database resources; the shared laptop adds contention. Recorded regressions are real and require controlled isolation.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E6 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E6; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 4. Is correctness guaranteed?

**Risk:** HIGH. **Likelihood:** HIGH.

**SHORT ANSWER:** Recorded settled oracle checks passed, but historical drift and stalls prevent a universal claim. A new mismatch blocks a correctness claim.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E2/E3 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E2/E3; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 5. Does tenant switching prove security?

**Risk:** HIGH. **Likelihood:** HIGH.

**SHORT ANSWER:** No. Authorization and forced RLS provide the boundaries; the operator-mode selector is not a negative security test.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 6. What if a scheduler stalls?

**Risk:** HIGH. **Likelihood:** HIGH.

**SHORT ANSWER:** Summaries can become stale. We expose refresh evidence and investigate backlog; we do not claim a guaranteed freshness bound.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E7 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E7; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 7. Why PostgreSQL?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** It keeps source transactions and maintained summaries in one database stack. The trade-off is maintenance competing with operational work.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 8. Why pg_trickle?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** It supplies differential view maintenance rather than rebuilding every summary. We credit upstream and measure its workload cost.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 9. Why not materialized views?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** Full refresh repeats computation. Differential maintenance is attractive for changing datasets but has its own overhead.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 10. Why not Redis?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** Caching repeats answers efficiently but requires correct invalidation. Our prototype maintains relational aggregates instead.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 11. Why not ClickHouse?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** A separate analytics store is a credible alternative. We chose a smaller PostgreSQL-centered prototype; no comparative benchmark proves superiority.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 12. Why not Kafka?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** A separate event pipeline adds operational components. Trigger-based capture fits our prototype; it still costs write work.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 13. Why not indexes?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** Indexes help selective reads, but repeated grouping can still be expensive. We have not proven our approach wins every workload.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 14. Why three stream tables?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** They cover product/day, category/day and category/hour groupings with status. They are fixed query-oriented summaries.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 15. Why raw edge reads?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** A partial time bucket cannot always be answered exactly from a complete bucket summary. Raw boundary queries preserve interval precision.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 16. How does sharding help?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** It separates tenant workloads across databases. It adds routing and operational complexity and does not remove hot-tenant bottlenecks.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E4/E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E4/E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 17. Is one-laptop sharding HA?

**Risk:** MEDIUM. **Likelihood:** HIGH.

**SHORT ANSWER:** No. Both databases share a failure domain. The recording demonstrates routing semantics only.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E4 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E4; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 18. What happens on cross-tenant requests?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** The API rejects unauthorized tenant access before routing. RLS is an additional boundary; secure-mode runtime rehearsal is still required here.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 19. What is forced RLS?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** It applies row policies even to a table owner in ordinary operation. Superuser and BYPASSRLS roles remain privileged exceptions.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 20. What about reused connections?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Tenant context is transaction-local. The transaction ends before the connection returns to the pool.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 21. Can operators bypass security?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** The local operator mode intentionally permits multiple tenants. It must never be presented as production tenant authentication.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E1/E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E1/E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 22. What auth limitations remain?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Fixed demo users and a shared demo password are not production identity management. Secret handling and deployment controls need production design.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 23. What about cancellation?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Changed status must remove the old contribution and add the new one. Recorded tests are bounded; rerun mutation/oracle checks before claiming current behavior.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E2/E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E2/E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 24. What if product changes?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Both grouping contributions must be updated. Verify the settled result against raw SQL rather than assuming delta handling is correct.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 25. How do you handle stale data?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Expose completed-refresh evidence and operational warnings. That evidence is not a commit-to-visible guarantee.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E1/E7 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E1/E7; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 26. What if refresh fails?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Report the failure and investigate; do not turn health green. Protected rebuild is recovery tooling, not a stage action.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E2/E7 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E2/E7; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 27. What if the oracle disagrees?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Retain output and investigate lag, snapshots and actual drift. Do not discard the failure or reseed preserved data.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E2/E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E2/E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 28. How does rebuild work?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** A protected CLI waits for completed rebuilds, checks active state and verifies with the oracle. Recorded wrong credentials fail closed.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E2/E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E2/E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 29. Did you meet 200ms?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Small recorded route p95s were below it. This does not qualify official dataset/concurrency performance.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E5 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E5; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 30. Always fresh within 30 seconds?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** No sustained guarantee is established. Small recorded visibility samples and refresh-age metadata answer different questions.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E5 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E5; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 31. Is your benchmark fair?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Existing exploratory runs are informative but limited and partly confounded. Matched repeated baseline and maintenance/load arms are next.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E6 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E6; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 32. How do you reach a billion records?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** We have no validated billion-row design. Partitioning, retention, hot-tenant placement and maintenance cost need measurement first.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 33. What about a huge tenant?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Per-tenant limits bound admitted work but do not solve all data skew. Dedicated placement and workload budgeting need evaluation.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 34. Why this problem and Mitigata relevance?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** Shared platforms need isolated analytics without harming operational traffic. Security-event rollups are a possible future application, not a current delivered feature.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 35. Is B4 implemented?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** No demonstrated configuration-driven metrics workflow is available. Our three summaries are fixed SQL definitions.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E8 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E8; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

## 36. Is monitoring fixed?

**Risk:** MEDIUM. **Likelihood:** MEDIUM.

**SHORT ANSWER:** No verified deployed complete repair is claimed. Newer dependency audit supersedes the earlier single-view plan.

**DEEP ANSWER:** The implementation and its evidence must be assessed separately. Open E7 in AUDIT_AND_EVIDENCE.md, show the relevant code or recorded conditions, and explain that a passing bounded test does not establish sustained production behavior. Our next acceptance gate is a reproducible run with the intended roles, dataset, concurrent workload and independent settled oracle.

**EVIDENCE:** E7; exact paths in evidence index.

**DO NOT SAY:** “Production proven”, “zero overhead”, “always correct”, or “official scale passed”.

