"""Live probe of PR #38 read_health as the real ax_monitor login (disposable ax-mh39 only)."""
import json, sys
sys.path.insert(0, sys.argv[1])
import psycopg
from psycopg.rows import dict_row
from axapi import monitor_health
with psycopg.connect("host=127.0.0.1 port=25590 dbname=aggregatex user=ax_monitor password=local-demo-monitor",
                     autocommit=True, row_factory=dict_row) as c:
    rows = monitor_health.read_health(c)
sev = {}
for r in rows: sev[r["severity"]] = sev.get(r["severity"], 0) + 1
mc = [r for r in rows if r["check_name"] == "monitor_contract"]
degraded = any(r["severity"] != "OK" for r in rows) or not rows
print(json.dumps({"rows": len(rows), "severities": sev, "monitor_contract": mc, "b5_degraded": degraded}))
