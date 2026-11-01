# G4 fix: runtime regression harness (#54, #67)

**What this is for.** PR #58 changes how pg_trickle reduces a row's changes inside one refresh. This harness checks the fix on a **real running PostgreSQL**, not just in unit tests. It runs the same tests twice:

| Run | Built from | Expected |
|---|---|---|
| `baseline-4bddde7` | the commit just before the fix (unpatched) | reproduces the bug: the product summary drifts in the insert→update and update→delete cases |
| `patched-cd6aed0` | the PR #58 fix | every case matches the source data exactly |

**Where it runs.** On a throwaway PostgreSQL 18 instance in a private scratch folder, on port 55432. It never uses Docker, the demo stacks or any shared database. `fixture.sql` refuses to run on anything except an empty `ax_g4_regress` database with the scheduler off.

**How a case works.**
1. The scheduler is **off**, so nothing refreshes by itself.
2. A case commits its changes as separate transactions, for example insert an order, then cancel it.
3. `check.sql` refreshes the three stream tables **once**, so the whole history lands in **one refresh window**. This is exactly where the bug lives.
4. It compares every stream table with a direct recomputation from `ax.orders` (`ax.oracle_mismatches()`, missing/extra rows) and records which refresh type ran.
5. A case **passes** only if all three tables match **and** every refresh was DIFFERENTIAL. A FULL or reinitialise refresh would hide the bug, so it counts as a failure.
6. If a case fails, the tables are rebuilt before the next case, so one failure can't affect later cases.

**Cases** (`cases.sql`):
- insert;
- insert → cancel (in one window, and across windows);
- update → delete;
- paid → cancelled → refunded;
- delete;
- insert → delete;
- quantity/price change;
- product move, and category move through `products`;
- `created_at` moved across a day/hour boundary;
- several orders in one group;
- rollback;
- a failed refresh, then a retry;
- primary key change;
- I-D-I-D-I and D-I-D histories;
- a 5-order mixed case;
- a long status history;
- two tenants in one window.

`rls.sql` checks that the `ax_api` role sees only its own tenant's rows, and none without a tenant setting.

**Run it:**
```bash
AX_SCRATCH=<private scratch dir> ./run.sh <label> <pg_trickle source checkout>
```
This builds pg_trickle and installs it into Homebrew `postgresql@18`. Output goes to `results/<label>/`: `summary.txt`, `results.json` and the logs.
