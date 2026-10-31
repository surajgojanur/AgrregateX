"""Bounded process-local metrics and operator monitoring. No tenant/path labels."""
import math
import threading
import time
from collections import deque
from datetime import datetime, timezone


class Metrics:
    def __init__(self, capacity=4096, window_s=300):
        self.samples = deque(maxlen=capacity)
        self.window_s = window_s
        self.lock = threading.Lock()

    def record(self, status, elapsed_ms, timeout=False):
        outcome = "timeout" if timeout or status in (408, 504) else "success" if status < 400 else "error"
        with self.lock:
            self.samples.append((time.monotonic(), outcome, elapsed_ms))

    def snapshot(self):
        with self.lock:
            rows = [r for r in self.samples if r[0] >= time.monotonic() - self.window_s]
        good = sorted(r[2] for r in rows if r[1] == "success")
        def percentile(p):
            return good[max(0, math.ceil(len(good) * p) - 1)] if good else None
        return {"success": sum(r[1] == "success" for r in rows),
                "errors": sum(r[1] == "error" for r in rows),
                "timeouts": sum(r[1] == "timeout" for r in rows),
                "p50_ms": percentile(.5), "p95_ms": percentile(.95),
                "window_s": self.window_s, "sample_capacity": self.samples.maxlen}


class RequestMetrics:
    def __init__(self, app, metrics):
        self.app, self.metrics = app, metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        start, status, timeout = time.monotonic(), 500, False
        async def capture(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
        try:
            await self.app(scope, receive, capture)
        except TimeoutError:
            timeout = True
            raise
        finally:
            self.metrics.record(status, round((time.monotonic() - start) * 1000, 2), timeout)


class ShardCache:
    """Single-flight cache; no background queries, at most one collection per TTL."""
    def __init__(self, collect, ttl=15):
        self.collect, self.ttl = collect, ttl
        self.lock = threading.Lock()
        self.value, self.expires = None, 0

    def get(self):
        with self.lock:
            if self.value is None or time.monotonic() >= self.expires:
                self.value = self.collect()
                self.expires = time.monotonic() + self.ttl
            return self.value


def collect_shards():
    from . import db, engine
    rows = []
    for name, shard in db.SHARDS.items():
        try:
            snap = engine.snapshot(name)
            with db.monitor(shard) as c:
                fresh = c.execute(engine.FRESHNESS_SQL, {"s": engine.ST_SCHEMA}).fetchall()
            fresh = [{**r, "verified_at": engine._iso(r["verified_at"]),
                      "age_s": float(r["age_s"]) if r["age_s"] is not None else None} for r in fresh]
            degraded = (not snap["scheduler_running"] or not fresh or
                        any(t["status"] != "ACTIVE" or t["consecutive_errors"] or
                            t["age_s"] is None or t["age_s"] >= 30 for t in fresh) or
                        any(r["failed"] for r in snap["refresh_stats_5m"]) or
                        any(h["severity"] in {"ERROR", "CRITICAL", "UNKNOWN"} for h in snap["health"]))
            rows.append({"shard": name, "state": "degraded" if degraded else "healthy",
                         "engine": snap, "freshness": fresh})
        except Exception:
            rows.append({"shard": name, "state": "unavailable", "detail": "Monitoring query failed; data unavailable."})
    return {"observed_at": datetime.now(timezone.utc).isoformat(), "shards": rows}


metrics = Metrics()
cache = ShardCache(collect_shards)


def install(app):
    from fastapi import APIRouter, Depends, HTTPException, Request
    from . import auth, limits
    router = APIRouter()

    def operator(request: Request):
        return auth.require_admin(request)

    @router.get("/api/monitoring")
    def monitoring(_user=Depends(operator)):
        return {**cache.get(), "api": metrics.snapshot(), "query_limits": limits.LIMITER.snapshot(), "cache_ttl_s": cache.ttl,
                "scope": "Process-local bounded 5-minute sample; resets on restart. Successful request latency only. Client-side timeouts cannot be observed."}

    app.add_middleware(RequestMetrics, metrics=metrics)
    app.include_router(router)
