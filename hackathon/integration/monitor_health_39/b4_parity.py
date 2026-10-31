"""B4/B5: facade (ax_monitor) vs native health_check (postgres) parity + stale_tables WARN rate."""
import json, sys, time, threading
import psycopg
from psycopg.rows import dict_row
label, seconds = sys.argv[1], float(sys.argv[2])
mon = psycopg.connect("host=127.0.0.1 port=25590 dbname=aggregatex user=ax_monitor password=local-demo-monitor", autocommit=True, row_factory=dict_row)
sup = psycopg.connect("host=127.0.0.1 port=25590 dbname=aggregatex user=postgres password=local-demo-superuser", autocommit=True, row_factory=dict_row)
def facade(): return {r["check_name"]: r["severity"] for r in mon.execute("SELECT check_name, severity FROM ax.monitor_health_check()")}
def native(): return {r["check_name"]: r["severity"] for r in sup.execute("SELECT check_name, severity FROM pgtrickle.health_check()")}
samples, diffs, stale_f, stale_n, contract, lat = 0, {}, 0, 0, {}, []
end = time.time() + seconds
while time.time() < end:
    out = {}
    t = threading.Thread(target=lambda: out.__setitem__("n", native())); t.start()
    t0 = time.perf_counter(); f = facade(); lat.append((time.perf_counter() - t0) * 1000); t.join()
    n = out["n"]; samples += 1
    c = f.pop("monitor_contract", None); contract[c] = contract.get(c, 0) + 1
    if set(f) != set(n): diffs["name_set"] = diffs.get("name_set", 0) + 1
    for k in set(f) & set(n):
        if f[k] != n[k]: diffs[k] = diffs.get(k, 0) + 1
    stale_f += f.get("stale_tables") != "OK"; stale_n += n.get("stale_tables") != "OK"
    time.sleep(0.2)
lat.sort()
print(json.dumps({"condition": label, "samples": samples, "monitor_contract": contract,
                  "severity_mismatches_by_check": diffs,
                  "stale_tables_non_ok_pct": {"facade": round(100 * stale_f / samples, 1), "native": round(100 * stale_n / samples, 1)},
                  "facade_latency_ms": {"p50": round(lat[len(lat)//2], 1), "p95": round(lat[int(len(lat)*.95)], 1), "max": round(lat[-1], 1)}}))
