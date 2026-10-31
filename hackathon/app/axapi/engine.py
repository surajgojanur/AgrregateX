"""pg_trickle engine internals, freshness and measured commit->visible lag.

Freshness rule (handoff F6): pgt_status().staleness / data_timestamp do not advance on
NO_DATA refreshes, so "verified as of" = end_time of the last COMPLETED refresh (any action).
Visibility rule: a committed change is visible in a stream table once that table's frontier
LSN for the source (pgt_stream_tables.frontier.sources.<oid>.lsn) >= the commit's WAL LSN.
"""
import random
import time
from datetime import datetime, timezone

from . import db

ST_SCHEMA = "ax"

FRESHNESS_SQL = """
SELECT st.pgt_name AS name, st.refresh_mode, st.effective_refresh_mode, st.status, st.schedule,
       st.consecutive_errors, h.end_time AS verified_at, h.action AS last_action,
       extract(epoch FROM clock_timestamp() - h.end_time) AS age_s
  FROM pgtrickle.pgt_stream_tables st
  LEFT JOIN LATERAL (SELECT end_time, action FROM pgtrickle.pgt_refresh_history r
                      WHERE r.pgt_id = st.pgt_id AND r.status = 'COMPLETED'
                      ORDER BY r.refresh_id DESC LIMIT 1) h ON true
 WHERE st.pgt_schema = %(s)s ORDER BY st.pgt_name"""


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def freshness() -> dict:
    with db.monitor_pool.connection() as c:
        rows = c.execute(FRESHNESS_SQL, {"s": ST_SCHEMA}).fetchall()
    tables = [{**r, "verified_at": _iso(r["verified_at"]),
               "age_s": round(float(r["age_s"]), 2) if r["age_s"] is not None else None} for r in rows]
    ages = [t["age_s"] for t in tables if t["age_s"] is not None]
    healthy = bool(tables) and all(t["status"] == "ACTIVE" for t in tables)
    return {"verified_age_s": max(ages) if ages and len(ages) == len(tables) else None,
            "healthy": healthy, "stream_tables": tables,
            "note": "verified_age_s = seconds since the OLDEST stream table last completed a refresh"}


def snapshot() -> dict:
    """Engine internals for the operator view (no tenant fact rows)."""
    with db.monitor_pool.connection() as c:
        version = c.execute("SELECT extversion FROM pg_extension WHERE extname = 'pg_trickle'").fetchone()
        sched = c.execute("SELECT count(*) AS n FROM pg_stat_activity WHERE backend_type = 'pg_trickle scheduler'"
                          " AND datname = current_database()").fetchone()
        tables = c.execute("""
            SELECT st.pgt_name AS name, st.refresh_mode, st.effective_refresh_mode, st.status,
                   st.requested_cdc_mode AS cdc_mode, st.schedule, st.consecutive_errors,
                   st.last_refresh_at, c.reltuples::bigint AS approx_rows,
                   pg_total_relation_size(st.pgt_relid) AS bytes
              FROM pgtrickle.pgt_stream_tables st JOIN pg_class c ON c.oid = st.pgt_relid
             WHERE st.pgt_schema = %(s)s ORDER BY st.pgt_name""", {"s": ST_SCHEMA}).fetchall()
        stats = c.execute("""
            SELECT st.pgt_name AS name, count(*) AS refreshes,
                   count(*) FILTER (WHERE h.action = 'DIFFERENTIAL') AS differential,
                   count(*) FILTER (WHERE h.action = 'FULL') AS full,
                   count(*) FILTER (WHERE h.action = 'NO_DATA') AS no_data,
                   count(*) FILTER (WHERE h.was_full_fallback) AS fallbacks,
                   count(*) FILTER (WHERE h.status = 'FAILED') AS failed,
                   COALESCE(sum(h.delta_row_count), 0)::bigint AS delta_rows,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM h.end_time - h.start_time) * 1000)
                          FILTER (WHERE h.action <> 'NO_DATA'))::numeric, 1) AS p50_ms,
                   round((percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM h.end_time - h.start_time) * 1000)
                          FILTER (WHERE h.action <> 'NO_DATA'))::numeric, 1) AS p95_ms,
                   round(max(extract(epoch FROM h.end_time - h.start_time) * 1000)::numeric, 1) AS max_ms
              FROM pgtrickle.pgt_refresh_history h JOIN pgtrickle.pgt_stream_tables st USING (pgt_id)
             WHERE st.pgt_schema = %(s)s AND h.start_time > now() - interval '5 minutes'
             GROUP BY st.pgt_name ORDER BY st.pgt_name""", {"s": ST_SCHEMA}).fetchall()
        recent = c.execute("""
            SELECT st.pgt_name AS name, h.action, h.status, h.start_time,
                   round((extract(epoch FROM h.end_time - h.start_time) * 1000)::numeric, 1) AS ms,
                   h.delta_row_count AS delta_rows,
                   COALESCE(h.rows_inserted, 0) + COALESCE(h.rows_updated, 0) + COALESCE(h.rows_deleted, 0) AS rows_changed,
                   h.was_full_fallback AS fallback, h.refresh_reason AS reason
              FROM pgtrickle.pgt_refresh_history h JOIN pgtrickle.pgt_stream_tables st USING (pgt_id)
             WHERE st.pgt_schema = %(s)s AND h.action <> 'NO_DATA'
             ORDER BY h.refresh_id DESC LIMIT 25""", {"s": ST_SCHEMA}).fetchall()
        buffers = c.execute("""
            SELECT c.relname AS buffer, COALESCE(s.n_live_tup, 0) AS pending_rows,
                   pg_total_relation_size(c.oid) AS bytes
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              LEFT JOIN pg_stat_all_tables s ON s.relid = c.oid
             WHERE n.nspname = 'pgtrickle_changes' AND c.relkind = 'r'
             ORDER BY c.relname""").fetchall()
        gucs = c.execute("""
            SELECT name, setting FROM pg_settings
             WHERE name IN ('pg_trickle.enabled', 'pg_trickle.cdc_mode', 'pg_trickle.min_schedule_seconds',
                            'pg_trickle.scheduler_interval_ms', 'pg_trickle.differential_max_change_ratio',
                            'pg_trickle.max_dynamic_refresh_workers', 'wal_level')
             ORDER BY name""").fetchall()
        try:
            health = c.execute("SELECT check_name, severity, detail FROM pgtrickle.health_check()").fetchall()
        except Exception as exc:  # noqa: BLE001 - surfaced to the operator, not hidden
            health = [{"check_name": "health_check", "severity": "UNKNOWN", "detail": str(exc).splitlines()[0]}]
    for row in tables:
        row["last_refresh_at"] = _iso(row["last_refresh_at"])
    for row in recent:
        row["start_time"] = _iso(row["start_time"])
    for row in stats:
        for k in ("p50_ms", "p95_ms", "max_ms"):
            row[k] = float(row[k]) if row[k] is not None else None
    for row in recent:
        row["ms"] = float(row["ms"]) if row["ms"] is not None else None
    return {"pg_trickle_version": version["extversion"] if version else None,
            "scheduler_running": bool(sched and sched["n"]),
            "stream_tables": tables, "refresh_stats_5m": stats, "recent_refreshes": recent,
            "change_buffers": buffers, "settings": {g["name"]: g["setting"] for g in gucs},
            "health": health}


def _frontier_lsns(c) -> dict:
    rows = c.execute("""
        SELECT st.pgt_name AS name,
               (st.frontier -> 'sources' -> ('ax.orders'::regclass::oid)::text ->> 'lsn')::pg_lsn AS lsn
          FROM pgtrickle.pgt_stream_tables st WHERE st.pgt_schema = %(s)s""", {"s": ST_SCHEMA}).fetchall()
    return {r["name"]: r["lsn"] for r in rows}


def live_write(tenant_id: int, action: str, order_id: int | None, timeout_s: float = 30.0) -> dict:
    """Commit one real source change for the tenant, then measure when each stream table covers it."""
    with db.tenant_tx(db.writer_pool, tenant_id) as c:
        if action == "insert":
            row = c.execute("""
                INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity,
                                       unit_price_cents, created_at)
                VALUES (%(t)s, nextval('ax.order_id_seq'), %(c)s, %(p)s, 'paid', %(q)s, %(u)s, now())
                RETURNING order_id, status""",
                            {"t": tenant_id, "c": random.randint(1, 1000), "p": random.randint(1, 200),
                             "q": random.randint(1, 5), "u": random.randint(500, 50000)}).fetchone()
        else:  # cancel
            row = c.execute("""
                UPDATE ax.orders SET status = 'cancelled', updated_at = now()
                 WHERE tenant_id = %(t)s AND order_id = %(o)s AND status <> 'cancelled'
                RETURNING order_id, status""", {"t": tenant_id, "o": order_id}).fetchone()
            if row is None:
                return {"error": "order not found for this tenant, or already cancelled"}
    # Transaction committed when the context exited. Any LSN read now is >= its commit record.
    t_commit = time.monotonic()
    committed_at = datetime.now(timezone.utc)
    with db.monitor_pool.connection() as c:
        target = c.execute("SELECT pg_current_wal_lsn() AS l").fetchone()["l"]
        visible_ms: dict[str, float | None] = {}
        while True:
            for name, lsn in _frontier_lsns(c).items():
                if name not in visible_ms and lsn is not None and _lsn_int(lsn) >= _lsn_int(target):
                    visible_ms[name] = round((time.monotonic() - t_commit) * 1000, 1)
            if len(visible_ms) >= 3 or time.monotonic() - t_commit > timeout_s:
                break
            time.sleep(0.025)
    lags = [v for v in visible_ms.values() if v is not None]
    return {"order_id": row["order_id"], "action": action, "status": row["status"],
            "committed_at": committed_at.isoformat(), "commit_lsn": str(target),
            "visible_after_ms": visible_ms, "timed_out": len(visible_ms) < 3,
            "lag_ms": max(lags) if len(lags) >= 3 else None}


def _lsn_int(lsn) -> int:
    hi, lo = str(lsn).split("/")
    return (int(hi, 16) << 32) | int(lo, 16)
