# RAW_CDC_TRACE — NOT COLLECTED

No target was started: resource preflight failed and target-specific approval is
absent. There are no newly committed source mutations and no observed runtime
CDC rows for cases A or B. Earlier Fedora history and the offline signed-event
model must not be represented as this experiment's raw trace.

Prepared collection is in trace_refresh.sql: privileged read of the explicitly
owned fixture's orders buffer into an external-output-preserved raw_before copy,
before refresh cleanup can run. Record change_id, LSN, action, complete row
identity, tenant/order/product/status, quantity, cents and timestamps; suppress
trace-context fields. Capture commit returns separately from server timestamps.
Filter that saved copy by the **actual** consumed before/after source frontiers.
Require A's three ordered images and B's two update images. Reject absent,
misordered, split-window or partially committed events as a capture/frontier
variant, never as observed staging loss.
