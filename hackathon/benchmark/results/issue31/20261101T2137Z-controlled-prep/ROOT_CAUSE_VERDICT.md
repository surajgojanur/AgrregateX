# ROOT_CAUSE_VERDICT — INCONCLUSIVE for controlled runtime confirmation

| Definition-of-done question | Actual answer |
|---|---|
| Did raw CDC contain the negative paid event? | UNKNOWN: no approved runtime experiment started. Expected by capture design, not observed here. |
| Was it removed during RLS staging? | UNKNOWN at runtime. Available-source reducer mathematically removes the intermediate D in the modeled three-image history. |
| Did direct aggregate receive two positive events? | UNKNOWN at runtime. Static P5 analysis predicts it for the modeled post-stage input. |
| Which generated delta/applied operation produced the incorrect row? | NOT OBSERVED in this experiment. Prior delete_insert history alone does not identify producer or stage contents. |
| Can one mechanism explain Fedora and Mac? | NOT ESTABLISHED. Candidate predicts Fedora both-statuses; Mac paid-only requires actual trace to distinguish windows/ordering/producer/apply. |
| Exact confirmed fix and tests? | No runtime-confirmed fix yet. Conditional keyed endpoint-normalization proposal and regression matrix are prepared, not patched or extension-tested. |
| Additional approvals? | Exact target approval plus passing resources; internal instrumentation/custom build separately if stock diagnostics cannot expose boundaries; later Rust patch and preserved-data repair separately. |

Prior evidence remains valid at its stated scope: Fedora persistent data/API
discrepancy, Mac reported 5/5 reproduction, statically demonstrated signed-input
loss. This new blocked attempt neither confirms nor disproves those findings.
No oracle PASS, staging-defect-confirmed, producer-defect or apply-defect verdict
is assigned without observed intermediate evidence.
