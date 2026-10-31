"""Runtime configuration (environment only; no secrets in code)."""
import os
import secrets

VERSION = "0.1.0"


def parse_analytics_read_mode(value: str | None) -> str:
    """Validate the server-side analytics source selector."""
    mode = "rollup" if value in (None, "") else value
    if mode not in {"rollup", "raw_source"}:
        raise ValueError("AX_ANALYTICS_READ_MODE must be 'rollup' or 'raw_source'")
    return mode


ANALYTICS_READ_MODE = parse_analytics_read_mode(os.environ.get("AX_ANALYTICS_READ_MODE"))


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    return value if value not in ("",) else default


DB_HOST = _env("AX_DB_HOST", "127.0.0.1")
DB_PORT = int(_env("AX_DB_PORT", "5432"))
DB_NAME = _env("AX_DB_NAME", "aggregatex")
API_PASSWORD = _env("AX_API_PASSWORD")
WRITER_PASSWORD = _env("AX_WRITER_PASSWORD")
MONITOR_PASSWORD = _env("AX_MONITOR_PASSWORD")

# Demo login: users tenant<N>@demo.local (tenant N) and admin@demo.local (operator).
DEMO_PASSWORD = _env("AX_DEMO_PASSWORD")
DEMO_TENANTS = int(_env("AX_DEMO_TENANTS", "10"))
# Signing key for session cookies. Random per process when unset (sessions end on restart).
SESSION_SECRET = (_env("AX_SESSION_SECRET") or secrets.token_hex(32)).encode()
SESSION_TTL_S = int(_env("AX_SESSION_TTL_S", "28800"))
COOKIE_SECURE = _env("AX_COOKIE_SECURE", "0") == "1"

# No-login mode: every request is the operator (local demo only; DB RLS still applies).
AUTH_DISABLED = _env("AX_AUTH_DISABLED", "0") == "1"
ENABLE_DEMO_WRITES = _env("AX_ENABLE_DEMO_WRITES", "0") == "1"
STATIC_DIR = _env("AX_STATIC_DIR")  # built frontend (dist/); served at / when set
MAX_RANGE_DAYS = 400
MAX_HOURLY_RANGE_DAYS = 31


# ── Sharding ──
# AX_SHARDS="a=shard_a:5432,b=shard_b:5432". Unset = one shard "default" at AX_DB_HOST:AX_DB_PORT.
def _parse_shards(raw: str | None) -> dict[str, tuple[str, int]]:
    if not raw:
        return {"default": (DB_HOST, DB_PORT)}
    out: dict[str, tuple[str, int]] = {}
    for item in raw.split(","):
        name, _, hostport = item.strip().partition("=")
        host, _, port = hostport.partition(":")
        if not name or not host:
            raise ValueError(f"bad AX_SHARDS entry: {item!r}")
        out[name] = (host, int(port or 5432))
    return out


SHARDS = _parse_shards(_env("AX_SHARDS"))
SHARD_DIRECTORY = _env("AX_SHARD_DIRECTORY")      # versioned tenant->shard JSON; required if >1 shard
CONNECT_TIMEOUT_S = int(_env("AX_CONNECT_TIMEOUT_S", "2"))
POOL_TIMEOUT_S = float(_env("AX_POOL_TIMEOUT_S", "3"))
STATEMENT_TIMEOUT_MS = int(_env("AX_STATEMENT_TIMEOUT_MS", "5000"))
# Client-side bound for a silently dropped network (Linux libpq): unacked data fails after this.
TCP_USER_TIMEOUT_MS = int(_env("AX_TCP_USER_TIMEOUT_MS", "3000"))


def dsn(user: str, password: str | None, host: str = DB_HOST, port: int = DB_PORT) -> str:
    parts = [f"host={host}", f"port={port}", f"dbname={DB_NAME}", f"user={user}",
             "application_name=aggregatex-api", f"connect_timeout={CONNECT_TIMEOUT_S}",
             "keepalives=1", "keepalives_idle=5", "keepalives_interval=2", "keepalives_count=2",
             f"tcp_user_timeout={TCP_USER_TIMEOUT_MS}"]
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)
