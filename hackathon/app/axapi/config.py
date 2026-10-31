"""Runtime configuration (environment only; no secrets in code)."""
import os
import secrets

VERSION = "0.1.0"


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


def dsn(user: str, password: str | None) -> str:
    parts = [f"host={DB_HOST}", f"port={DB_PORT}", f"dbname={DB_NAME}", f"user={user}",
             "application_name=aggregatex-api", "connect_timeout=3"]
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)
