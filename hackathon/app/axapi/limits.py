"""B-3: per-tenant limit on concurrent heavy analytics queries.

Each tenant gets its own bounded slot pool (AX_TENANT_MAX_CONCURRENT, default 4). A request waits at
most AX_TENANT_QUEUE_WAIT_S (default 0.25 s) for a slot, then is rejected with HTTP 429 and
Retry-After, so one busy tenant can never occupy every database connection and starve the others.
Scope: per API process (the demo runs one uvicorn worker). With several workers the effective
per-tenant limit is workers x AX_TENANT_MAX_CONCURRENT.
"""
import os
import threading
from collections import Counter
from contextlib import contextmanager


class TenantBusy(Exception):
    def __init__(self, tenant_id: int, limit: int):
        super().__init__(f"tenant {tenant_id} is at its concurrency limit ({limit})")
        self.tenant_id = tenant_id
        self.limit = limit


class TenantLimiter:
    def __init__(self, max_concurrent: int, wait_s: float):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self.max_concurrent = max_concurrent
        self.wait_s = wait_s
        self._lock = threading.Lock()
        self._slots: dict[int, threading.BoundedSemaphore] = {}
        self._in_flight: Counter = Counter()
        self._admitted: Counter = Counter()
        self._rejected: Counter = Counter()
        self._peak: Counter = Counter()

    def _slot(self, tenant_id: int) -> threading.BoundedSemaphore:
        with self._lock:
            sem = self._slots.get(tenant_id)
            if sem is None:
                sem = self._slots[tenant_id] = threading.BoundedSemaphore(self.max_concurrent)
            return sem

    @contextmanager
    def slot(self, tenant_id: int):
        sem = self._slot(tenant_id)
        if not sem.acquire(timeout=self.wait_s):
            with self._lock:
                self._rejected[tenant_id] += 1
            raise TenantBusy(tenant_id, self.max_concurrent)
        with self._lock:
            self._in_flight[tenant_id] += 1
            self._admitted[tenant_id] += 1
            self._peak[tenant_id] = max(self._peak[tenant_id], self._in_flight[tenant_id])
        try:
            yield
        finally:
            with self._lock:
                self._in_flight[tenant_id] -= 1
            sem.release()

    def snapshot(self) -> dict:
        with self._lock:
            tenants = sorted(set(self._admitted) | set(self._rejected))
            return {
                "max_concurrent_per_tenant": self.max_concurrent,
                "queue_wait_s": self.wait_s,
                "scope": "per API process",
                "tenants": [{"tenant_id": t, "in_flight": self._in_flight[t], "peak": self._peak[t],
                             "admitted": self._admitted[t], "rejected_429": self._rejected[t]} for t in tenants],
            }


LIMITER = TenantLimiter(int(os.environ.get("AX_TENANT_MAX_CONCURRENT", "4")),
                        float(os.environ.get("AX_TENANT_QUEUE_WAIT_S", "0.25")))
