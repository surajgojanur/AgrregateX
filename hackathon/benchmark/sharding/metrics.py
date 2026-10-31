"""Summarize observed samples only; absent metrics remain NOT TESTED."""
import json, statistics, sys, time, urllib.error, urllib.request

def percentile(xs, p):
    ys=sorted(xs)
    return ys[min(len(ys)-1, max(0, int((len(ys)-1)*p)))]

def measure(url, count=30, timeout=3):
    samples=[]; failures=0
    for _ in range(count):
        start=time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                response.read()
                if response.status != 200: failures+=1
        except (OSError, urllib.error.URLError): failures+=1
        samples.append((time.perf_counter()-start)*1000)
    good=[x for x in samples if x < timeout*1000]
    return {"requests":count,"failures":failures,"latency_ms":{"p50":percentile(good,.5),"p95":percentile(good,.95)} if good else None}

if __name__ == '__main__':
    if len(sys.argv)!=2: raise SystemExit('usage: metrics.py <health-or-tenant-url>')
    print(json.dumps({"status":"MEASURED","url":sys.argv[1],"observed":measure(sys.argv[1])},indent=2))
