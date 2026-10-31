# G1–G5 scorecard

Scope: preserved Fedora synthetic small demo (1002 orders). No official acceptance.

| Goal | Good | Great | Measured evidence | Status |
|---|---|---|---|---|
| G1 | <1 s | <200 ms at 10M | 16 HTTP samples; p50/p95/p99 3.459352/12.227789/12.227789 ms; errors 0, timeouts 0 | NOT TESTED at scale |
| G2 | <5 min | <30 s | No Fedora writes authorized; Mac #46: 18/20 >30s timeouts | NOT TESTED locally; Mac Great failed |
| G3 | <25% slowdown | <10% slowdown | Mac PR #46 matched 5 pairs, confounded by host freezes | INCOMPLETE |
| G4 | Most match | All match | 16 selected-field API comparisons, 0 failures; exact stream differences in comparison.json | FAIL (small demo) |
| G5 | <5× | <2× | No matched 1M/10M HTTP measurements | NOT TESTED |

Raw evidence: [HTTP](http/http.json), [SQL comparisons](sql-corrected/comparison.json), [exact SQL](sql-corrected/executed.sql), [drift detail](drift.txt).

G4 is a snapshot failure, not a proven engine root cause. No external-writer quiescence guarantee. API subset excludes the affected tenant/product interval. No tenant-isolation, adversarial tie, full boundary or mutation qualification.

Historical Mac 100k/1M generator evidence is documented in `hackathon/integration/scale/README.md`; no raw 1M HTTP run exists. Mac G3 source: [PR #46 report at 1d653de](https://github.com/surajgojanur/AgrregateX/blob/1d653de/hackathon/integration/g3/results/10k-o200-r20-matched/REPORT.md). No Fedora tuning or teammate files changed.
