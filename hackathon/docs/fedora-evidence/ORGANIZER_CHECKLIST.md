# Organizer dataset compatibility checklist

The checked-in sample data is representative. The organizer schema and official
generator have not been verified. Do not silently map assumptions into an
official result.

| Item to confirm | Current AgrregateX assumption | Organizer answer / status |
|---|---|---|
| Source schema / keys | `tenant_id`, `order_id`, product/customer IDs in `ax.orders` | UNKNOWN — obtain DDL and primary-key rules. |
| Tenant distribution | Tenants can be skewed; sharding directory maps tenants to one DB | UNKNOWN — obtain per-tenant target row counts and required skew profile. |
| Status vocabulary | `pending`, `paid`, `shipped`, `cancelled`, `refunded` in representative source | UNKNOWN — confirm exhaustive values, casing, and transitions. |
| Cancellation/refund behavior | Current demo excludes `cancelled` and `refunded` from sales; status breakdown still counts them | UNKNOWN — confirm whether sales mean gross/net and whether tax, discounts, refunds, and cancellations change totals. |
| Monetary precision | Integer cents / line totals in representative data | UNKNOWN — confirm currency, decimal precision, quantity multiplication, rounding, tax and currency mixing. |
| Time columns | UTC-derived day/hour buckets; partial range edges read raw orders | UNKNOWN — confirm timestamp meaning, source timezone, daylight-saving handling, inclusive/exclusive boundaries. |
| Late edits | Updates should move prior status/time/product groups; deletes are included in oracle scenarios | UNKNOWN — confirm allowed update/delete behavior and historical correction window. |
| Generator | No organizer generator artifact is available in this repository | UNKNOWN — request exact generator, version, seed, command and deterministic behavior. |
| Dataset manifest | Benchmarks should record row counts per tenant and dataset identity | UNKNOWN — request expected totals, checksum, tenant counts and skew metrics for 1M/10M sets. |
| Query contract | Current REST endpoints and revenue ranking are project proposals | UNKNOWN — confirm required dimensions, ranking semantics/tie-breaks, time ranges and response schema. |

Before official scorecard runs: pin the official generator and seed; record
source and tenant counts; map columns explicitly; settle money/time/status
semantics; run oracle checks after insert, update, cancellation and delete; keep
representative and organizer datasets in separate result labels.
