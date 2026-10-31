# STAGING_TRACE — NOT COLLECTED; internal-boundary visibility unverified

The approved resource/target gate did not pass. No staging rows were observed.
Current stage-loss evidence remains static analysis/offline arithmetic only.

First diagnostic attempt after approval: manual refresh inside one explicit
transaction, then same-backend SELECT from
`pg_temp.__pgt_cdc_<pgt_id>_<orders_oid>` before COMMIT. Release source indicates
ON COMMIT DROP lifetime. This would observe actual post-compaction **and**
post-visibility-filter contents if the installed binary follows that lifetime.
Never try to access another backend's temp relation or assume its contents.

The raw-buffer capture is not an observed internal pre-compaction stage. To
attribute removal specifically to the reducer rather than visibility filtering,
need the real staged rows immediately after copy, after reducer, and after
owner-visible filtering, correlated to the same source LSN range and snapshot.
Nested statement diagnostics may show the two DELETE plans/row counts but not
their exact payloads. If those boundaries cannot be observed, stop that subtask.

Minimum separately approved instrumentation: diagnostic-only bounded snapshots
at these three points in DeltaStage::stage_source, keyed by run/case/pgt/source,
PID, snapshot, before/new frontier, change_id, LSN, I/D action, encoded identity
and synthetic payload. Limit <=100 orders and <=1000 events; error rather than
truncate silently. Exclude session secrets and trace context. No event rewrites,
extra commits, waits or reducer correction. Save logs outside database; avoid
table observers/triggers that change semantics. Custom Rust build is NOT
authorized or attempted by this packet; it requires separate build/resource scope
and cannot masquerade as an unmodified release-binary confirmation.
