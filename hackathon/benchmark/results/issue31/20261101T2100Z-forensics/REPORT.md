# G4 forensic investigation — PERSISTENT OBSERVED

Secondary classification: **ENGINE DEFECT SUSPECTED**, not a locally confirmed engine bug.
Preserved Fedora `round1-db`, database `aggregatex`, PostgreSQL 18.6,
pg_trickle 0.108.3; diagnostics ran as `postgres`. Operator API bypass remains
enabled: these observations do not qualify RLS or secure tenant authentication.
Repository/PR head before investigation: `74f1e5051e6976a21716c6bde8e28ee49e050c47`;
fetched main: `c19b89a24370d29412fc42c250a86b0ea68f791f`.

## Repeated exact comparisons

Five separate REPEATABLE READ READ ONLY transactions used the same three-table
symmetric EXCEPT ALL SELECTs as the original oracle, with explicit output aliases,
2-second statement timeout and 500-ms lock timeout. See `observation-summary.json`
for exact UTC times, snapshot identifiers, counts and final content fingerprints.
`snapshots.sql` is the executed SQL for observations 1–3;
`snapshots-with-digests.sql` adds content fingerprints and the exact group for 4–5.
There was no polling loop or database-side sleep. Raw outputs are retained.

Every observation has **day-product 0 missing / 1 extra**, **day-category 0/0**,
**hour-category 0/0**, with 1,002 source orders. The original 20:50 UTC failure
is preserved in the earlier directory; the new observations begin at 21:00 UTC.
The discrepancy did not disappear. Final paired fingerprints cover explicitly
selected source/aggregate columns, exclude extension-internal columns, and test
whether those contents changed; MD5 is a change indicator, not artifact security.
Refresh metadata advances even while aggregate contents remain unchanged.

## Exact source and stream group

`group.sql` / `group.txt` establish the following from source data, not rollups:

- One source row: `order_id=100000000`, tenant 2, product 116, **cancelled**,
  quantity 1, unit price 14,094 cents.
- `created_at=2026-10-31T10:38:56.233003Z`,
  `updated_at=2026-10-31T10:39:26.275213Z`.
- Expected paid aggregate: **0 orders, 0 units, 0 cents**; no paid group should exist.
- Expected cancelled aggregate: **1 order, 1 unit, 14,094 gross cents**.
- Day-product stream has both the correct cancelled group and an additional
  paid group with the same count/units/cents. Each key occurs once: this is a
  **ghost paid group**, not duplicate rows for an identical grouping key.
- Product 116 maps to category 9. Day/category and 10:00 UTC hour/category both
  contain only the correct cancelled aggregate for this category/day.

`created_at` is timestamptz; UTC buckets are timestamp without time zone.
Session timezone was Etc/UTC. The oracle explicitly uses
`date_trunc(..., created_at AT TIME ZONE 'UTC')`. All 1,002 source rows have
stored day/hour buckets and line cents equal to independently recomputed values.
The order lies well inside the day/hour, not on a boundary. Captured defining
queries group on stored UTC buckets and line cents, equivalent for this dataset.
Numeric/bigint aggregate types do not explain an additional paid group.
The corrected oracle is not demonstrated defective; the original duplicate-alias
capture error remains historical and was not used for these conclusions.

## Refresh, CDC and historical activity

`history.sql` / `history.txt` show:

- All three streams ACTIVE, configured DIFFERENTIAL, effective NO_DATA;
  zero consecutive errors, no reinit request, no tentative frontier.
- Latest completed refresh timestamps advance during the observation interval.
  The scheduler backend is present, and recent NO_DATA jobs complete roughly
  every 1–2 seconds. No current scheduler failure is established.
- No recorded FAILED/incomplete refresh or FULL fallback in the retained history.
  Initial FULL and schema-change REINITIALIZE records exist; these are not
  fallback records and were not triggered by this investigation.
- Product stream history: a DIFFERENTIAL at 10:39:57 inserted two aggregate rows;
  a 10:39:58 DIFFERENTIAL had zero delta; later 11:11:51/58 records exist.
  The first two-row delta follows the source row's creation and update times.
  This timing is consistent with processing multiple images in one delta,
  **but history does not identify those rows or prove the earlier status**.
- CDC mode is TRIGGER. Each source buffer contains exactly one row, `action='S'`,
  `lsn='0/0'`, with null business keys. These are synthetic sentinel rows,
  consistent with the sentinel representation in repository `src/cdc/mod.rs`.
  There are **zero observed real pending change rows**, not a one-row backlog.
  Trigger-mode LSN receipt/ack fields are null, not evidence of unconsumed WAL.
- Other observed database sessions were idle; the scheduler was waiting in
  Extension. This is a point observation, not proof that no external writer exists.

Repeated completed NO_DATA actions, sentinel-only buffers, stable source data and
old source timestamps argue strongly against ordinary refresh delay. Available
catch-up indicators support persistence, but transaction history/audit logs and
complete external-writer quiescence were not established.

## Customer-visible API impact

Six serial GETs, each with a two-second client timeout, all returned HTTP 200 for
tenant 2 over `[2026-10-31T00:00:00Z, 2026-11-01T00:00:00Z)`.
Exact URLs/responses are in `api.json`; independent source SQL and snapshot are
in `api-source-and-buffers.sql` / `.txt`. No login/write request was made.

| API | Actual | Expected from source | Result |
|---|---|---|---|
| Summary | 2 orders, 1 sale order/unit, 14,094 sales cents | 1 order, 0 sale orders/units/cents | FAIL |
| Top products | product 116 with 14,094 sales cents | empty (only order is cancelled) | FAIL |
| Status breakdown | cancelled and paid, one each | cancelled only | FAIL |
| Daily trends | 1 order, 0 sales cents, 1 cancelled | same | MATCH |
| Hourly trends | 10:00 bucket: 1 order, 0 sales cents, 1 cancelled | same | MATCH |
| Category breakdown | category 9: 1 order, 0 sale units/cents | same | MATCH |

Full-day requests report no raw edge ranges. Summary/top/status use the affected
product stream; trends/category use the correctly maintained category streams.
Freshness metadata simultaneously reports healthy with ~1.31-second age: this
confirms why refresh-age metadata alone cannot prove correctness or write visibility.
API and source SQL are separate observations; repeated stable snapshots support
the comparison but do not make them one atomic HTTP/SQL snapshot.

## Explanation, limits and next action

**A real persistent aggregate/API correctness discrepancy is established in the
observed database. Its precise historical cause is not established locally.**
The strongest explanation is retained paid-state maintenance drift associated
with an earlier update/cancellation, rather than transient lag, timezone conversion
or a faulty expected aggregate. Direct historical stream edits or other unrecorded
operations cannot be ruled out from these diagnostics.

Corroboration only: teammate PR #49 at commit
`5c8580b62f4738e22709b24c3e5f7c2053fd8cba` includes
`hackathon/integration/scale/repro_insert_update_drift.sql` and
`hackathon/integration/scale/results/REPORT-1m.md`, reporting 5/5 same-delta
insert/update drift in the product stream while joined streams remain correct.
Those files were read, never executed or modified. Their reported manifestation
(paid retained, cancelled absent) differs from Fedora (both groups present), so
equating the exact causal path would overstate the evidence.

Smallest next safe step: a read-only review of the single-source aggregate delta
netting path against the teammate's recorded reproduction and this two-group
variant. Any local controlled reproduction needs a separately approved disposable
target; any Rust fix or data repair needs separate scope/authorization. Do not
rebuild this demo to make the failure disappear. G4 remains FAIL for this dataset.

## Safety and validation

No DML, DDL, GRANT, migration, refresh/rebuild call, scheduler setting change,
container/service stop/restart, new stack, network fault, dataset load or upstream
edit. Only transaction-local read/timeout controls, SELECTs and six analytics GETs.
SQL uses the existing postgres diagnostic role, not an RLS acceptance identity.
Historical evidence is untouched; all new artifacts are in this new directory.
Raw text has trailing whitespace normalized; business values are unmodified.
SHA256SUMS.json protects the published artifact bytes. No credentials/config dumps.

Existing 25 benchmark/acceptance tests and offline capture-consistency checks were
rerun; see `validation.txt`. `just fmt`/`just lint` availability is recorded there;
no Rust validation success is claimed when tooling is absent. PR #48 remains draft.
