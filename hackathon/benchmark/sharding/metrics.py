"""HTTP metrics with successful latency separated from errors/timeouts."""
import json
import math
import sys
import time
import urllib.error
import urllib.request

def percentile_nearest_rank(values, p):
    if not values:
        return None
    xs = sorted(values)
    index = max(0, math.ceil(p * len(xs)) - 1)
    return xs[index]

def measure(url, count=30, timeout=3):
    success_ms, errors, timeouts = [], [], 0
    for _ in range(count):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                response.read()
                elapsed = (time.perf_counter() - started) * 1000
                if 200 <= response.status < 300:
                    success_ms.append(elapsed)
                else:
                    errors.append({"status": response.status, "elapsed_ms": elapsed})
        except urllib.error.HTTPError as exc:
            elapsed = (time.perf_counter() - started) * 1000
            errors.append({"status": exc.code, "elapsed_ms": elapsed})
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
                timeouts += 1
            else:
                errors.append({"error": type(exc).__name__})
    return {"requests": count, "successes": len(success_ms), "errors": errors,
            "timeouts": timeouts,
            "successful_latency_ms_nearest_rank": {
                "p50": percentile_nearest_rank(success_ms, .50),
                "p95": percentile_nearest_rank(success_ms, .95)}}

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: metrics.py <health-or-tenant-url>')
    print(json.dumps({"status": "OBSERVED", "url": sys.argv[1],
                      "metrics": measure(sys.argv[1])}, indent=2))
