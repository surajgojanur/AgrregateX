# Scale evidence review

`verify_scale_evidence.py` independently checks the internal arithmetic and
cross-file consistency of the 1M and 10M representative scale artifacts. It does
not contact PostgreSQL, the API, Docker, or GitHub and never grants official
acceptance.

Run from the repository root after PR #57 artifacts are available in the working
tree:

```bash
python3 hackathon/benchmark/evidence_review/verify_scale_evidence.py \
  hackathon/integration/scale/results \
  --source-commit b0f360685c33f67516c6ef0c1c6170b1575d14ee \
  --json-out hackathon/benchmark/evidence_review/EVIDENCE_AUDIT.json \
  --markdown-out hackathon/benchmark/evidence_review/EVIDENCE_AUDIT.md
```

For local verification before PR #57 is merged, the same command accepts an
extracted/read-only PR artifact directory as its input. The committed report
identifies the exact audited PR head.

Run offline adversarial tests:

```bash
python3 -m unittest discover -s hackathon/benchmark/evidence_review -v
```

The checker verifies the 72 endpoint/tenant-rank/window identities, duplicate
and missing cases, 50-sample counts, status/error totals, finite and ordered
aggregate latency fields, scenario/summary consistency, role sizes, matched
1M/10M scenario p95 pairs, ratio arithmetic, dataset snapshot counts, 100-tenant
count comparison, and the initial-load three-table oracle output. It does not
recompute p50/p95/p99 from raw samples because the source artifacts do not
contain per-request timings.

“VALIDATED FROM ARTIFACT” means the artifact's fields agree and arithmetic was
recomputed. It is not proof that the source run occurred. “REPORTED BUT NOT
INDEPENDENTLY RECOMPUTABLE” records a source claim that cannot be reproduced
from stored detail. “INSUFFICIENT EVIDENCE” marks missing qualification data.
The output's `official_pass` is always false.
