"""Shard-aware connection routing.

Every shard is an independent PostgreSQL + pg_trickle instance with its own pools for the three
roles (ax_api tenant reads, ax_writer tenant writes, ax_monitor engine catalog). A tenant is
routed to exactly one shard by the versioned directory (AX_SHARD_DIRECTORY). There is NO
cross-shard fallback: if the owning shard is unreachable the call raises ShardUnavailable
(-> HTTP 503) within bounded time (connect timeout, pool wait, TCP user timeout, statement timeout).

Without AX_SHARDS the API runs one shard named "default" and every tenant routes to it.
"""
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from . import config


class ShardUnavailable(Exception):
    def __init__(self, shard: str, reason: str = ""):
        super().__init__(f"shard {shard} unavailable: {reason}")
        self.shard = shard
        self.reason = reason


class UnknownTenant(Exception):
    pass


def _pool(name: str, user: str, password: str | None, host: str, port: int, size: int, autocommit=False):
    return ConnectionPool(
        config.dsn(user, password, host, port), min_size=0, max_size=size, open=False, name=name,
        timeout=config.POOL_TIMEOUT_S, reconnect_timeout=30, check=ConnectionPool.check_connection,
        kwargs={"row_factory": dict_row, "autocommit": autocommit,
                "options": f"-c statement_timeout={config.STATEMENT_TIMEOUT_MS}"})


@dataclass
class Shard:
    name: str
    host: str
    port: int
    api: ConnectionPool = field(init=False)
    writer: ConnectionPool = field(init=False)
    monitor: ConnectionPool = field(init=False)

    def __post_init__(self):
        n, h, p = self.name, self.host, self.port
        self.api = _pool(f"{n}.ax_api", "ax_api", config.API_PASSWORD, h, p, 8)
        self.writer = _pool(f"{n}.ax_writer", "ax_writer", config.WRITER_PASSWORD, h, p, 3)
        self.monitor = _pool(f"{n}.ax_monitor", "ax_monitor", config.MONITOR_PASSWORD, h, p, 3, autocommit=True)

    @property
    def pools(self):
        return (self.api, self.writer, self.monitor)


SHARDS: dict[str, Shard] = {n: Shard(n, h, p) for n, (h, p) in config.SHARDS.items()}


def _load_directory() -> tuple[int | None, dict[int, str]]:
    if not config.SHARD_DIRECTORY:
        if len(SHARDS) > 1:
            raise RuntimeError("AX_SHARD_DIRECTORY is required when more than one shard is configured")
        return None, {}
    with open(config.SHARD_DIRECTORY, encoding="utf-8") as fh:
        data = json.load(fh)
    tenants = {int(t): s for t, s in data["tenants"].items()}
    unknown = sorted({s for s in tenants.values() if s not in SHARDS})
    if unknown:
        raise RuntimeError(f"directory v{data.get('version')} references unconfigured shards: {unknown}")
    return int(data["version"]), tenants


DIRECTORY_VERSION, DIRECTORY = _load_directory()


def shard_for(tenant_id: int) -> Shard:
    if not DIRECTORY:  # single-shard mode
        return next(iter(SHARDS.values()))
    name = DIRECTORY.get(int(tenant_id))
    if name is None:
        raise UnknownTenant(tenant_id)
    return SHARDS[name]


def tenants_of(shard: str) -> list[int]:
    return sorted(t for t, s in DIRECTORY.items() if s == shard)


def open_all() -> None:
    for shard in SHARDS.values():
        for pool in shard.pools:
            pool.open(wait=False)


def close_all() -> None:
    for shard in SHARDS.values():
        for pool in shard.pools:
            pool.close(timeout=2)


_UNAVAILABLE = (PoolTimeout, psycopg.OperationalError, psycopg.errors.QueryCanceled)


@contextmanager
def tenant_tx(role: str, tenant_id: int):
    """One transaction on the tenant's OWNING shard with ax.tenant_id set LOCAL.

    role: "api" (reads) or "writer". The setting dies with the transaction, so pooled
    connections never leak a tenant; without it RLS returns no rows (fail closed).
    """
    shard = shard_for(tenant_id)
    pool = shard.api if role == "api" else shard.writer
    try:
        with pool.connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('ax.tenant_id', %s, true)", (str(int(tenant_id)),))
                yield conn
    except _UNAVAILABLE as exc:
        raise ShardUnavailable(shard.name, type(exc).__name__) from exc


@contextmanager
def monitor(shard: Shard):
    try:
        with shard.monitor.connection() as conn:
            yield conn
    except _UNAVAILABLE as exc:
        raise ShardUnavailable(shard.name, type(exc).__name__) from exc


def probe(shard: Shard) -> dict:
    """Bounded liveness probe used by /api/health and /api/shards."""
    t0 = time.monotonic()
    try:
        with monitor(shard) as c:
            c.execute("SELECT 1").fetchone()
        return {"available": True, "probe_ms": round((time.monotonic() - t0) * 1000, 1)}
    except ShardUnavailable as exc:
        return {"available": False, "probe_ms": round((time.monotonic() - t0) * 1000, 1), "error": exc.reason}
