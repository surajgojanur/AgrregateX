"""pg_trickle engine internals, freshness and measured commit->visible lag.

Freshness rule (handoff F6): pgt_status().staleness / data_timestamp do not advance on
NO_DATA refreshes, so "verified as of" = end_time of the last COMPLETED refresh (any action).
Visibility rule (data-based): a committed change is visible in a stream table once, in ONE
snapshot, the stream table's row for every group the change touched equals the same aggregate
computed from raw ax.orders. (An LSN rule is unreliable: pg_trickle's frontier records the LSN
of the last consumed change, which is below the commit LSN and does not move while idle.)
"""
import random
import threading
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


def freshness(tenant_id: int) -> dict:
    shard = db.shard_for(tenant_id)
    with db.monitor(shard) as c:
        rows = c.execute(FRESHNESS_SQL, {"s": ST_SCHEMA}).fetchall()
    tables = [{**r, "verified_at": _iso(r["verified_at"]),
               "age_s": round(float(r["age_s"]), 2) if r["age_s"] is not None else None} for r in rows]
    ages = [t["age_s"] for t in tables if t["age_s"] is not None]
    healthy = bool(tables) and all(t["status"] == "ACTIVE" for t in tables)
    return {"shard": shard.name, "verified_age_s": max(ages) if ages and len(ages) == len(tables) else None,
            "healthy": healthy, "stream_tables": tables,
            "note": "verified_age_s = seconds since the OLDEST stream table last completed a refresh"}


_BRIEF_TTL_S = 1.0
_brief_cache: dict[str, tuple[float, dict]] = {}
_brief_locks: dict[str, threading.Lock] = {}
_brief_locks_guard = threading.Lock()


def _brief_lock(shard_name: str) -> threading.Lock:
    with _brief_locks_guard:
        return _brief_locks.setdefault(shard_name, threading.Lock())


def freshness_brief(shard: "db.Shard") -> dict:
    """B-1: compact freshness for analytics responses. verified_at = the OLDEST stream table's last
    completed refresh (any action, including NO_DATA), so every number in the response is at least
    that fresh. Single-flight per shard with a 1 s cache: concurrent misses wait for one query, so it
    costs at most one catalog query per second per shard (PR #24 review)."""
    hit = _brief_cache.get(shard.name)
    if hit and time.monotonic() - hit[0] < _BRIEF_TTL_S:
        return hit[1]
    with _brief_lock(shard.name):
        hit = _brief_cache.get(shard.name)          # another request may have refreshed it meanwhile
        if hit and time.monotonic() - hit[0] < _BRIEF_TTL_S:
            return hit[1]
        with db.monitor(shard) as c:
            rows = c.execute(FRESHNESS_SQL, {"s": ST_SCHEMA}).fetchall()
        times = [r["verified_at"] for r in rows if r["verified_at"] is not None]
        complete = bool(rows) and len(times) == len(rows)
        brief = {
            "verified_at": _iso(min(times)) if complete else None,
            "age_s": round(max(float(r["age_s"]) for r in rows), 2) if complete else None,
            "healthy": complete and all(r["status"] == "ACTIVE" for r in rows),
            "stream_tables": len(rows),
            "rule": "oldest stream table's last completed refresh",
        }
        _brief_cache[shard.name] = (time.monotonic(), brief)
        return brief


def snapshot(shard_name: str) -> dict:
    """Engine internals of ONE shard for the operator view (no tenant fact rows)."""
    shard = db.SHARDS[shard_name]
    with db.monitor(shard) as c:
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
    return {"shard": shard.name, "pg_trickle_version": version["extversion"] if version else None,
            "scheduler_running": bool(sched and sched["n"]),
            "stream_tables": tables, "refresh_stats_5m": stats, "recent_refreshes": recent,
            "change_buffers": buffers, "settings": {g["name"]: g["setting"] for g in gucs},
            "health": health}


# For each stream table: does its row for the touched group equal the raw-orders aggregate?
_GROUP_CHECK = """
SELECT
  (SELECT (COALESCE(sum(order_count), 0)::bigint, COALESCE(sum(sales_cents), 0)::numeric) FROM ax.st_day_product_status
    WHERE tenant_id = %(t)s AND utc_day = %(d)s AND product_id = %(p)s AND status = %(s)s)
  = (SELECT (count(*)::bigint, COALESCE(sum(line_cents), 0)::numeric) FROM ax.orders
      WHERE tenant_id = %(t)s AND utc_day = %(d)s AND product_id = %(p)s AND status = %(s)s) AS st_day_product_status,
  (SELECT (COALESCE(sum(order_count), 0)::bigint, COALESCE(sum(sales_cents), 0)::numeric) FROM ax.st_day_category_status
    WHERE tenant_id = %(t)s AND utc_day = %(d)s AND category_id = %(c)s AND status = %(s)s)
  = (SELECT (count(*)::bigint, COALESCE(sum(o.line_cents), 0)::numeric) FROM ax.orders o
       JOIN ax.products p ON p.tenant_id = o.tenant_id AND p.product_id = o.product_id
      WHERE o.tenant_id = %(t)s AND o.utc_day = %(d)s AND p.category_id = %(c)s AND o.status = %(s)s) AS st_day_category_status,
  (SELECT (COALESCE(sum(order_count), 0)::bigint, COALESCE(sum(sales_cents), 0)::numeric) FROM ax.st_hour_category_status
    WHERE tenant_id = %(t)s AND utc_hour = %(h)s AND category_id = %(c)s AND status = %(s)s)
  = (SELECT (count(*)::bigint, COALESCE(sum(o.line_cents), 0)::numeric) FROM ax.orders o
       JOIN ax.products p ON p.tenant_id = o.tenant_id AND p.product_id = o.product_id
      WHERE o.tenant_id = %(t)s AND o.utc_hour = %(h)s AND p.category_id = %(c)s AND o.status = %(s)s) AS st_hour_category_status
"""
_ROW = "o.order_id, o.status, o.utc_day, o.utc_hour, o.product_id"  # writer role cannot read products


def live_write(tenant_id: int, action: str, order_id: int | None, timeout_s: float = 30.0) -> dict:
    """Commit one real source change for the tenant, then measure when each stream table reflects it."""
    shard = db.shard_for(tenant_id)
    with db.tenant_tx("writer", tenant_id) as c:
        if action == "insert":
            row = c.execute(f"""
                WITH o AS (
                  INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity,
                                         unit_price_cents, created_at)
                  VALUES (%(t)s, nextval('ax.order_id_seq'), %(c)s, %(p)s, 'paid', %(q)s, %(u)s, now())
                  RETURNING *)
                SELECT {_ROW}, NULL::text AS old_status FROM o""",
                            {"t": tenant_id, "c": random.randint(1, 1000), "p": random.randint(1, 200),
                             "q": random.randint(1, 5), "u": random.randint(500, 50000)}).fetchone()
        else:  # cancel
            old = c.execute("""SELECT status FROM ax.orders WHERE tenant_id = %(t)s AND order_id = %(o)s
                                 AND status <> 'cancelled' FOR UPDATE""", {"t": tenant_id, "o": order_id}).fetchone()
            if old is None:
                return {"error": "order not found for this tenant, or already cancelled"}
            row = c.execute(f"""
                WITH o AS (UPDATE ax.orders SET status = 'cancelled', updated_at = now()
                            WHERE tenant_id = %(t)s AND order_id = %(o)s RETURNING *)
                SELECT {_ROW}, %(old)s::text AS old_status FROM o""",
                            {"t": tenant_id, "o": order_id, "old": old["status"]}).fetchone()
    # Reaching this line means COMMIT succeeded (a failed or unacknowledged commit raised
    # ShardUnavailable -> 503, never a success).
    t_commit = time.monotonic()
    committed_at = datetime.now(timezone.utc)
    groups = [row["status"]] + ([row["old_status"]] if row["old_status"] else [])
    visible_ms: dict[str, float] = {}
    visibility_error = None
    try:  # the write is committed; an outage now must NOT turn it into a reported failure
        with db.tenant_tx("api", tenant_id) as rc:   # category via the read role (least privilege)
            cat = rc.execute("SELECT category_id FROM ax.products WHERE tenant_id = %s AND product_id = %s",
                             (tenant_id, row["product_id"])).fetchone()
        row = {**row, "category_id": cat["category_id"] if cat else None}
        while True:
            with db.tenant_tx("api", tenant_id) as rc:
                ok = {}
                for status in groups:
                    r = rc.execute(_GROUP_CHECK, {"t": tenant_id, "d": row["utc_day"], "h": row["utc_hour"],
                                                  "p": row["product_id"], "c": row["category_id"], "s": status}).fetchone()
                    for k, v in r.items():
                        ok[k] = ok.get(k, True) and bool(v)
            for name, good in ok.items():
                if good and name not in visible_ms:
                    visible_ms[name] = round((time.monotonic() - t_commit) * 1000, 1)
            if len(visible_ms) >= 3 or time.monotonic() - t_commit > timeout_s:
                break
            time.sleep(0.025)
    except db.ShardUnavailable as exc:
        visibility_error = f"committed, but visibility could not be measured: {exc.reason}"
    return {"shard": shard.name, "committed": True, "order_id": row["order_id"], "action": action,
            "status": row["status"], "committed_at": committed_at.isoformat(),
            "groups_checked": groups, "visible_after_ms": visible_ms, "timed_out": len(visible_ms) < 3,
            "lag_ms": max(visible_ms.values()) if len(visible_ms) >= 3 else None,
            "visibility_error": visibility_error}


def shard_status(shard: db.Shard) -> dict:
    """Health, tenants, refresh state and CDC backlog of one shard. Never raises for an outage."""
    out = {"shard": shard.name, "host": shard.host, "tenants": db.tenants_of(shard.name) if db.DIRECTORY else None,
           **db.probe(shard)}
    if not out["available"]:
        return out
    try:
        with db.monitor(shard) as c:
            out["stream_tables"] = [{**r, "verified_at": _iso(r["verified_at"]),
                                     "age_s": round(float(r["age_s"]), 2) if r["age_s"] is not None else None}
                                    for r in c.execute(FRESHNESS_SQL, {"s": ST_SCHEMA}).fetchall()]
            out["pending_cdc_rows"] = c.execute("""
                SELECT COALESCE(sum(s.n_live_tup), 0)::bigint AS n FROM pg_stat_all_tables s
                 WHERE s.schemaname = 'pgtrickle_changes'""").fetchone()["n"]
            counts = c.execute("SELECT tenant_id, orders, seed_orders FROM ax.tenant_order_counts() ORDER BY 1").fetchall()
        out["orders_by_tenant"] = counts
        out["orders"] = sum(r["orders"] for r in counts)
        out["seed_orders"] = sum(r["seed_orders"] for r in counts)
        stray = sorted({r["tenant_id"] for r in counts} - set(out["tenants"] or []))
        out["directory_violations"] = stray if db.DIRECTORY else []
        out["healthy"] = all(t["status"] == "ACTIVE" for t in out["stream_tables"]) and not out["directory_violations"]
    except db.ShardUnavailable as exc:
        out.update(available=False, error=exc.reason)
    return out


def shards_overview() -> dict:
    shards = [shard_status(s) for s in db.SHARDS.values()]
    missing = [s["shard"] for s in shards if not s["available"]]
    complete = not missing
    total = sum(s.get("orders", 0) for s in shards if s["available"])
    return {
        "directory_version": db.DIRECTORY_VERSION,
        "complete": complete,
        "missing_shards": missing,
        # A global total is only reported when EVERY shard answered; otherwise it is explicitly partial.
        "total_orders": total if complete else None,
        "partial_total_orders": None if complete else total,
        "shards": shards,
    }
