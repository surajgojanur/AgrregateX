"""B-2: rebuild every AggregateX number from scratch, then prove it with the oracle.

Operator CLI, deliberately NOT a web endpoint: pg_trickle only lets the stream-table OWNER (the
database superuser here) reinitialize, and it checks the session's *outer* user, so a SECURITY
DEFINER wrapper is refused by design. Keeping superuser credentials out of the web API is the safer
trade-off; the operator supplies them for the duration of one command.

For each stream table on the selected shard(s):
  1. pgtrickle.reinitialize_stream_table(name): drops the incremental state and schedules a
     protected FULL recompute from the source tables;
  2. wait until pgt_refresh_history shows a COMPLETED REINITIALIZE/FULL refresh that started after
     the request (bounded by --timeout);
  3. verify: ax.oracle_mismatches() must be 0/0 for all three stream tables (retried briefly,
     because live writes may still be in flight).
Prints a JSON report; exit 0 only if every stream table rebuilt AND the oracle is clean.

usage (inside the API container, or anywhere that can reach the shards):
  AX_DB_SUPERUSER_PASSWORD=... python -m axapi.rebuild [--shard a|b|all] [--timeout 120]
"""
import argparse
import json
import os
import sys
import time

import psycopg

from . import config, db

ST_NAMES = ("ax.st_day_product_status", "ax.st_day_category_status", "ax.st_hour_category_status")


def _connect(shard: "db.Shard", user: str, password: str | None):
    conn = psycopg.connect(config.dsn(user, password, shard.host, shard.port), autocommit=True)
    conn.execute("SET statement_timeout = '120s'")
    return conn


def rebuild_shard(shard: "db.Shard", user: str, password: str | None, timeout_s: float) -> dict:
    t0 = time.monotonic()
    report = {"shard": shard.name, "stream_tables": [], "oracle": None, "ok": False}
    with _connect(shard, user, password) as c:
        started = c.execute("SELECT clock_timestamp()").fetchone()[0]
        for st in ST_NAMES:
            rows_before = c.execute(f"SELECT count(*) FROM {st}").fetchone()[0]
            msg = c.execute("SELECT pgtrickle.reinitialize_stream_table(%s)", (st,)).fetchone()[0]
            report["stream_tables"].append({"name": st, "rows_before": rows_before, "reinitialize": msg})
        # Wait for the protected full rebuild of every stream table.
        pending = set(ST_NAMES)
        while pending and time.monotonic() - t0 < timeout_s:
            for item in report["stream_tables"]:
                if item["name"] not in pending:
                    continue
                schema, name = item["name"].split(".")
                r = c.execute("""
                    SELECT h.action, h.status, round(extract(epoch FROM h.end_time - h.start_time) * 1000) AS ms
                      FROM pgtrickle.pgt_refresh_history h JOIN pgtrickle.pgt_stream_tables s USING (pgt_id)
                     WHERE s.pgt_schema = %s AND s.pgt_name = %s AND h.start_time >= %s
                       AND h.action IN ('REINITIALIZE', 'FULL') AND h.status IN ('COMPLETED', 'FAILED')
                     ORDER BY h.refresh_id DESC LIMIT 1""", (schema, name, started)).fetchone()
                if r:
                    item.update(rebuild_action=r[0], rebuild_status=r[1], rebuild_ms=float(r[2] or 0))
                    item["rows_after"] = c.execute(f"SELECT count(*) FROM {item['name']}").fetchone()[0]
                    pending.discard(item["name"])
            if pending:
                time.sleep(0.5)
        for item in report["stream_tables"]:
            if item["name"] in pending:
                item["rebuild_status"] = "TIMEOUT"
        statuses = {r[0]: r[1] for r in c.execute(
            "SELECT pgt_schema || '.' || pgt_name, status FROM pgtrickle.pgt_stream_tables WHERE pgt_schema = 'ax'")}
        for item in report["stream_tables"]:
            item["status_after"] = statuses.get(item["name"])
        # Verify against the raw source (retry: live writes may be mid-refresh).
        for attempt in range(1, 16):
            rows = c.execute("SELECT stream_table, missing_in_st, extra_in_st FROM ax.oracle_mismatches()").fetchall()
            report["oracle"] = {"attempt": attempt, "rows": [{"stream_table": a, "missing": m, "extra": e} for a, m, e in rows]}
            if all(m == 0 and e == 0 for _, m, e in rows):
                break
            time.sleep(2)
    rebuilt = all(i.get("rebuild_status") == "COMPLETED" and i.get("status_after") == "ACTIVE" for i in report["stream_tables"])
    clean = report["oracle"] is not None and all(r["missing"] == 0 and r["extra"] == 0 for r in report["oracle"]["rows"])
    report.update(ok=rebuilt and clean, rebuilt=rebuilt, oracle_clean=clean,
                  seconds=round(time.monotonic() - t0, 2))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="B-2: rebuild all AggregateX stream tables from scratch and verify.")
    ap.add_argument("--shard", default="all", help="shard name or 'all' (default)")
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds to wait per shard for the rebuild")
    ap.add_argument("--user", default=os.environ.get("AX_DB_SUPERUSER", "postgres"), help="stream-table owner role")
    args = ap.parse_args(argv)
    password = os.environ.get("AX_DB_SUPERUSER_PASSWORD")
    if not password:
        print("AX_DB_SUPERUSER_PASSWORD is required (stream-table owner); it is never stored by the API.", file=sys.stderr)
        return 2
    names = list(db.SHARDS) if args.shard == "all" else [args.shard]
    unknown = [n for n in names if n not in db.SHARDS]
    if unknown:
        print(f"unknown shard(s): {unknown}; configured: {list(db.SHARDS)}", file=sys.stderr)
        return 2
    reports = []
    for n in names:
        try:
            reports.append(rebuild_shard(db.SHARDS[n], args.user, password, args.timeout))
        except psycopg.Error as exc:
            reports.append({"shard": n, "ok": False, "error": str(exc).splitlines()[0]})
    ok = all(r.get("ok") for r in reports)
    print(json.dumps({"ok": ok, "shards": reports}, indent=1, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
