#!/usr/bin/env python3
"""Sequential, GET-only smoke checks for a loopback AgrregateX demo."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

TIMEOUT_S = 4
DEFAULT_BASE = "http://127.0.0.1:8093"


def validate_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("base URL must be plain HTTP on a loopback IP address")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise ValueError("base URL must use a loopback IP literal") from exc
    if not address.is_loopback or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("base URL must point directly to a loopback service")
    if parsed.port is None or not 1 <= parsed.port <= 65535:
        raise ValueError("base URL must include a valid port")
    return f"http://{parsed.netloc}"


def routes(tenant_id: int) -> tuple[str, ...]:
    if not 1 <= tenant_id <= 998:
        raise ValueError("tenant id must be between 1 and 998")
    prefix = f"/api/tenants/{tenant_id}"
    return (
        "/api/health",
        "/api/tenants",
        f"{prefix}/summary",
        f"{prefix}/trends",
        f"{prefix}/top-products",
        f"{prefix}/breakdown?by=status",
        f"{prefix}/breakdown?by=category",
        f"{prefix}/freshness",
        "/api/shards",
        "/api/engine",
        "/api/monitoring",
        "/api/limits",
    )


def _safe_opener():
    """Never use environment proxies or follow redirects outside localhost."""
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None
    return build_opener(ProxyHandler({}), NoRedirect())


def _valid_payload(path: str, body: object) -> bool:
    """Small smoke contract; HTTP 200 or syntactically valid JSON is not enough."""
    if not isinstance(body, dict):
        return False
    if path == "/api/health":
        return isinstance(body.get("status"), str) and isinstance(body.get("shards"), dict)
    if path == "/api/shards":
        shards = body.get("shards")
        return (type(body.get("complete")) is bool and isinstance(shards, list)
                and "total_orders" in body
                and all(isinstance(shard, dict) and isinstance(shard.get("stream_tables"), list)
                        and all(isinstance(st, dict) and isinstance(st.get("name"), str) for st in shard["stream_tables"])
                        for shard in shards))
    if path == "/api/tenants":
        return isinstance(body.get("tenants"), list)
    if path == "/api/engine":
        return isinstance(body.get("stream_tables"), list) and "health" in body
    if path == "/api/monitoring":
        return isinstance(body.get("shards"), list) and isinstance(body.get("api"), dict)
    if path == "/api/limits":
        return "tenants" in body and "max_concurrent_per_tenant" in body
    if path.endswith("/summary"):
        return type(body.get("tenant_id")) is int and isinstance(body.get("summary"), dict)
    if path.endswith("/trends"):
        return isinstance(body.get("points"), list) and "grain" in body
    if path.endswith("/top-products"):
        return isinstance(body.get("products"), list) and "limit" in body
    if "/breakdown?" in path:
        return isinstance(body.get("rows"), list) and "by" in body
    if path.endswith("/freshness"):
        return isinstance(body.get("stream_tables"), list) and "healthy" in body
    return False


def _summary(path: str, body: object) -> dict:
    if not isinstance(body, dict):
        return {"shape": type(body).__name__}
    result = {"keys": sorted(body.keys())}
    if path == "/api/health":
        result.update(status=body.get("status"), pg_trickle_version=body.get("pg_trickle_version"),
                      shards=sorted((body.get("shards") or {}).keys()))
    elif path == "/api/shards":
        shards = body.get("shards") or []
        result.update(complete=body.get("complete"), total_orders=body.get("total_orders"),
                      shards=[{"name": s.get("shard"), "available": s.get("available"),
                               "orders": s.get("orders"), "seed_orders": s.get("seed_orders"),
                               "stream_tables": sorted(t.get("name") for t in s.get("stream_tables", []))}
                              for s in shards])
    elif path.endswith("/freshness"):
        result.update(healthy=body.get("healthy"), verified_age_s=body.get("verified_age_s"),
                      stream_tables=body.get("stream_tables"))
    return result


def run(base: str, tenant_id: int) -> tuple[list[dict], bool]:
    base = validate_base_url(base)
    report = []
    opener = _safe_opener()
    for path in routes(tenant_id):
        started = time.monotonic()
        row = {"method": "GET", "path": path}
        try:
            request = Request(base + path, method="GET", headers={"Accept": "application/json"})
            with opener.open(request, timeout=TIMEOUT_S) as response:
                payload = response.read(128 * 1024)
                row.update(status=response.status, latency_ms=round((time.monotonic() - started) * 1000, 1))
            try:
                body = json.loads(payload)
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = None
            valid = _valid_payload(path, body)
            row["response_schema_valid"] = valid
            row.update(response=_summary(path, body) if valid else {"shape": type(body).__name__})
            if not valid:
                row["error"] = "invalid_json_or_schema"
        except HTTPError as exc:
            row.update(status=exc.code, latency_ms=round((time.monotonic() - started) * 1000, 1),
                       error="redirect_blocked" if 300 <= exc.code < 400 else "http_error")
            exc.close()
        except (TimeoutError, URLError, OSError) as exc:
            timed_out = isinstance(exc, TimeoutError) or "timed out" in str(exc).lower()
            row.update(status=None, latency_ms=round((time.monotonic() - started) * 1000, 1),
                       error="timeout" if timed_out else "connection_error")
        report.append(row)
    ok = all(type(row.get("status")) is int and 200 <= row["status"] < 300
             and row.get("response_schema_valid") is True for row in report)
    return report, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="loopback base URL (default: %(default)s)")
    parser.add_argument("--tenant-id", type=int, default=1, help="tenant for analytics GETs (default: 1)")
    args = parser.parse_args(argv)
    try:
        report, ok = run(args.base_url, args.tenant_id)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"mode": "sequential_get_only", "timeout_s": TIMEOUT_S,
                      "auth": "uses current local demo mode; does not log in",
                      "writes": False, "checks": report}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
