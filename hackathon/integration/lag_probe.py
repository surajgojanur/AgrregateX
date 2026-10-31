"""Commit->visible lag probe for AgrregateX stream tables (client-side, autocommit).

Polls from a separate autocommit connection so no long transaction holds back the
pg_trickle frontier (a server-side polling loop does: "frontier holdback active").
Uses probe tenant 999 (created by spike_lib.sql). Test-only.

usage: python3 -I lag_probe.py <label> [samples] [dsn]
"""
import json
import random
import statistics
import sys
import time

import psycopg2

label = sys.argv[1]
samples = int(sys.argv[2]) if len(sys.argv) > 2 else 15
dsn = sys.argv[3] if len(sys.argv) > 3 else (
    "host=127.0.0.1 port=25540 user=postgres dbname=tenant_gen password=spike-only-not-secret")
TIMEOUT_S = 120.0

w = psycopg2.connect(dsn); w.autocommit = True
r = psycopg2.connect(dsn); r.autocommit = True
wc, rc = w.cursor(), r.cursor()


def visible(sql):
    rc.execute(sql)
    return rc.fetchone()[0]


def wait_until(pred_sql, before):
    t0 = time.monotonic()
    while True:
        if visible(pred_sql) > before:
            return (time.monotonic() - t0) * 1000.0
        if time.monotonic() - t0 > TIMEOUT_S:
            return None
        time.sleep(0.01)


CNT = "SELECT COALESCE(sum(order_count),0) FROM ax.st_day_product_status WHERE tenant_id=999"
CAN = CNT + " AND status='cancelled'"
res = {"insert": [], "cancel": [], "timeouts": 0}
for _ in range(samples):
    wc.execute("SELECT COALESCE(max(order_id),0)+1 FROM ax.orders WHERE tenant_id=999")
    oid = wc.fetchone()[0]
    before = visible(CNT)
    wc.execute("INSERT INTO ax.orders (tenant_id,order_id,customer_id,product_id,status,quantity,"
               "unit_price_cents,created_at) VALUES (999,%s,1,1,'paid',1,1000,now())", (oid,))
    lag = wait_until(CNT, before)  # autocommit: INSERT already committed when execute returns
    res["insert"].append(lag) if lag is not None else res.__setitem__("timeouts", res["timeouts"] + 1)
    before = visible(CAN)
    wc.execute("UPDATE ax.orders SET status='cancelled' WHERE tenant_id=999 AND order_id=%s", (oid,))
    lag = wait_until(CAN, before)
    res["cancel"].append(lag) if lag is not None else res.__setitem__("timeouts", res["timeouts"] + 1)
    time.sleep(random.random() * 0.7)  # de-phase from scheduler tick

out = {"label": label, "samples": samples, "timeouts": res["timeouts"]}
for k in ("insert", "cancel"):
    v = sorted(res[k])
    if v:
        out[k] = {"n": len(v), "p50_ms": round(statistics.median(v), 1),
                  "p95_ms": round(v[min(len(v) - 1, int(0.95 * len(v)))], 1), "max_ms": round(v[-1], 1)}
print(json.dumps(out))
