"""AgrregateX API: tenant-safe analytics over pg_trickle stream tables (+ built UI)."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config, db, engine, limits, queries, raw_queries

UTC = timezone.utc


@asynccontextmanager
async def lifespan(_app):
    db.open_all()
    yield
    db.close_all()


app = FastAPI(title="AgrregateX API", version=config.VERSION, lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(db.ShardUnavailable)
async def shard_unavailable(_req: Request, exc: db.ShardUnavailable):
    # Fail closed: no cross-shard fallback, no partial answer dressed up as a full one.
    return JSONResponse({"detail": f"Shard {exc.shard} is unavailable. Data for tenants on this shard cannot be "
                                   "read or written right now; nothing was served from another shard.",
                         "shard": exc.shard, "retryable": True},
                        status_code=503, headers={"Retry-After": "5"})


@app.exception_handler(limits.TenantBusy)
async def tenant_busy(_req: Request, exc: limits.TenantBusy):
    # B-3: one tenant cannot monopolise the database; other tenants keep their own slots.
    return JSONResponse({"detail": f"Too many concurrent analytics queries for tenant {exc.tenant_id} "
                                   f"(limit {exc.limit}). Retry shortly.",
                         "tenant_id": exc.tenant_id, "limit": exc.limit, "retryable": True},
                        status_code=429, headers={"Retry-After": "1"})


@app.exception_handler(Exception)
async def unhandled(_req: Request, exc: Exception):  # never leak SQL/stack traces to clients
    return JSONResponse({"detail": "Internal error."}, status_code=500)


# ── window parsing ──────────────────────────────────────────────────────────
def _parse(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, f"Invalid timestamp: {value!r} (use ISO 8601).") from exc
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def window(from_: str | None = Query(None, alias="from"), to: str | None = Query(None)):
    end = _parse(to, datetime.now(UTC))
    start = _parse(from_, end - timedelta(days=30))
    if start >= end:
        raise HTTPException(422, "'from' must be before 'to'.")
    if end - start > timedelta(days=config.MAX_RANGE_DAYS):
        raise HTTPException(422, f"Range is limited to {config.MAX_RANGE_DAYS} days.")
    return start, end


def _meta(tenant_id: int, start: datetime, end: datetime, w: queries.Window,
          *, family: str, breakdown_by: str | None = None, **extra) -> dict:
    mode = config.ANALYTICS_READ_MODE
    rollup_sources = {
        "summary": ["ax.st_day_product_status", "ax.orders"],
        "trends_day": ["ax.st_day_category_status", "ax.orders"],
        "trends_hour": ["ax.st_hour_category_status", "ax.orders"],
        "top_products": ["ax.st_day_product_status", "ax.orders", "ax.products"],
        "breakdown_status": ["ax.st_day_product_status", "ax.orders"],
        "breakdown_category": ["ax.st_day_category_status", "ax.orders", "ax.products"],
    }
    if mode == "raw_source":
        source = {"stream_table_range": None,
                  "raw_edge_ranges": [[start.isoformat(), end.isoformat()]]}
        needs_products = family == "top_products" or (family == "breakdown" and breakdown_by == "category")
        source_tables = ["ax.orders", "ax.products"] if needs_products else ["ax.orders"]
        provenance = {"source_tables": source_tables, "uses_stream_tables": False,
                      "consistency": "single_sql_statement_snapshot"}
    else:
        has_full = w.full_lo < w.full_hi
        edges = [[start.isoformat(), w.edge1_end.isoformat()]] if start < w.edge1_end else []
        if w.edge2_start < end and has_full:
            edges.append([w.edge2_start.isoformat(), end.isoformat()])
        source = {"stream_table_range": [w.full_lo.replace(tzinfo=UTC).isoformat(),
                                         w.full_hi.replace(tzinfo=UTC).isoformat()] if has_full else None,
                  "raw_edge_ranges": edges}
        source_key = f"trends_{extra.get('grain')}" if family == "trends" else \
                     f"breakdown_{breakdown_by}" if family == "breakdown" else family
        provenance = {"source_tables": rollup_sources[source_key],
                      "uses_stream_tables": True, "consistency": "single_sql_statement_snapshot"}
    return {"tenant_id": tenant_id, "shard": db.shard_for(tenant_id).name,
            "from": start.isoformat(), "to": end.isoformat(), "source": source,
            "analytics_mode": mode, "provenance": provenance, **extra}


def _run(fn, tenant_id, *args):
    """Heavy analytics query under the tenant's B-3 slot, then its B-1 freshness (same shard)."""
    mode = config.ANALYTICS_READ_MODE
    if mode == "raw_source":
        fn = {"summary": raw_queries.summary, "trends": raw_queries.trends,
              "top_products": raw_queries.top_products, "breakdown": raw_queries.breakdown}[fn.__name__]
    with limits.LIMITER.slot(tenant_id), db.tenant_tx("api", tenant_id) as conn:
        data = fn(conn, tenant_id, *args)
    # Stream refresh age does not describe source-derived answers and may lag them.
    fresh = engine.freshness_brief(db.shard_for(tenant_id)) if mode == "rollup" else None
    return data, fresh


# ── auth ───────────────────────────────────────────────────────────────────
class Login(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(body: Login, response: Response):
    user = auth.lookup(body.email)
    if user is None or not auth.check_password(body.password):
        raise HTTPException(401, "Incorrect email or password.")
    response.set_cookie(auth.COOKIE, auth.issue(user), max_age=config.SESSION_TTL_S, httponly=True,
                        samesite="lax", secure=config.COOKIE_SECURE, path="/")
    return {"user": user.public()}


@app.post("/api/auth/register")
def register():
    raise HTTPException(403, "Self-registration is disabled in this demo. Use a tenant<N>@demo.local account.")


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(auth.COOKIE, path="/")


@app.get("/api/auth/me")
def me(user: auth.User = Depends(auth.current_user)):
    return {"user": user.public()}


# ── health / directory ─────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    shards = {name: db.probe(sh) for name, sh in db.SHARDS.items()}
    up = [n for n, p in shards.items() if p["available"]]
    version = None
    for name in up:
        try:
            with db.monitor(db.SHARDS[name]) as c:
                v = c.execute("SELECT extversion FROM pg_extension WHERE extname = 'pg_trickle'").fetchone()
            version = v["extversion"] if v else None
            break
        except db.ShardUnavailable:
            continue
    status = "ok" if len(up) == len(shards) else ("degraded" if up else "down")
    body = {"status": status, "version": config.VERSION, "database": "ok" if status == "ok" else status,
            "pg_trickle_version": version, "shards": shards, "directory_version": db.DIRECTORY_VERSION}
    return JSONResponse(body, status_code=200 if up else 503)


@app.get("/api/tenants")
def tenants(user: auth.User = Depends(auth.current_user)):
    if db.DIRECTORY:  # served from the directory, so it still answers while a shard is down
        rows = [{"tenant_id": t, "name": f"tenant-{t}", "shard": s} for t, s in sorted(db.DIRECTORY.items())]
    else:
        shard = next(iter(db.SHARDS.values()))
        with db.monitor(shard) as c:
            rows = [{**r, "shard": shard.name} for r in
                    c.execute("SELECT tenant_id, name FROM ax.tenants WHERE tenant_id < 999 ORDER BY tenant_id").fetchall()]
    return {"directory_version": db.DIRECTORY_VERSION,
            "tenants": [r for r in rows if user.can_read_tenant(r["tenant_id"])]}


# ── tenant analytics ───────────────────────────────────────────────────────
def tenant_path(tenant_id: int, user: auth.User = Depends(auth.current_user)) -> int:
    auth.authorize_tenant(user, tenant_id)          # authorisation BEFORE routing
    try:
        db.shard_for(tenant_id)
    except db.UnknownTenant as exc:
        raise HTTPException(404, "Unknown tenant.") from exc
    return tenant_id


@app.get("/api/tenants/{tenant_id}/summary")
async def summary(tenant_id: int = Depends(tenant_path), win=Depends(window)):
    w = queries.split(*win, "day")
    data, fresh = await run_in_threadpool(_run, queries.summary, tenant_id, w)
    return _meta(tenant_id, *win, w, family="summary", freshness=fresh, summary=data)


@app.get("/api/tenants/{tenant_id}/trends")
async def trends(tenant_id: int = Depends(tenant_path), win=Depends(window),
                 grain: Literal["day", "hour"] = "day"):
    if grain == "hour" and win[1] - win[0] > timedelta(days=config.MAX_HOURLY_RANGE_DAYS):
        raise HTTPException(422, f"Hourly trends are limited to {config.MAX_HOURLY_RANGE_DAYS} days.")
    w = queries.split(*win, grain)
    data, fresh = await run_in_threadpool(_run, queries.trends, tenant_id, w, grain)
    return _meta(tenant_id, *win, w, family="trends", freshness=fresh, grain=grain, points=data)


@app.get("/api/tenants/{tenant_id}/top-products")
async def top_products(tenant_id: int = Depends(tenant_path), win=Depends(window),
                       limit: int = Query(10, ge=1, le=50)):
    w = queries.split(*win, "day")
    data, fresh = await run_in_threadpool(_run, queries.top_products, tenant_id, w, limit)
    return _meta(tenant_id, *win, w, family="top_products", freshness=fresh, limit=limit, products=data)


@app.get("/api/tenants/{tenant_id}/breakdown")
async def breakdown(tenant_id: int = Depends(tenant_path), win=Depends(window),
                    by: Literal["status", "category"] = "status"):
    w = queries.split(*win, "day")
    data, fresh = await run_in_threadpool(_run, queries.breakdown, tenant_id, w, by)
    return _meta(tenant_id, *win, w, family="breakdown", breakdown_by=by,
                 freshness=fresh, by=by, rows=data)


@app.get("/api/tenants/{tenant_id}/freshness")
async def freshness(tenant_id: int = Depends(tenant_path)):
    return {"tenant_id": tenant_id, **await run_in_threadpool(engine.freshness, tenant_id)}


class LiveWrite(BaseModel):
    action: Literal["insert", "cancel"] = "insert"
    order_id: int | None = None


@app.post("/api/tenants/{tenant_id}/live-write")
async def live_write(body: LiveWrite, tenant_id: int = Depends(tenant_path)):
    if not config.ENABLE_DEMO_WRITES:
        raise HTTPException(403, "Demo writes are disabled (AX_ENABLE_DEMO_WRITES=1 to enable).")
    if body.action == "cancel" and body.order_id is None:
        raise HTTPException(422, "order_id is required to cancel.")
    result = await run_in_threadpool(engine.live_write, tenant_id, body.action, body.order_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return {"tenant_id": tenant_id, **result}


# ── operator ───────────────────────────────────────────────────────────────
@app.get("/api/engine")
async def engine_snapshot(shard: str | None = None, _admin: auth.User = Depends(auth.require_admin)):
    name = shard or next(iter(db.SHARDS))
    if name not in db.SHARDS:
        raise HTTPException(404, "Unknown shard.")
    return {"shards": list(db.SHARDS), **await run_in_threadpool(engine.snapshot, name)}


@app.get("/api/limits")
def tenant_limits(_admin: auth.User = Depends(auth.require_admin)):
    """B-3 counters: per-tenant in-flight, peak, admitted and 429-rejected analytics queries."""
    return limits.LIMITER.snapshot()


@app.get("/api/shards")
async def shards(_admin: auth.User = Depends(auth.require_admin)):
    return await run_in_threadpool(engine.shards_overview)


from .monitoring import install as install_monitoring
install_monitoring(app)


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_not_found(rest: str):
    raise HTTPException(404, "Not found.")


# ── built frontend (single-port demo) ──────────────────────────────────────
if config.STATIC_DIR and Path(config.STATIC_DIR, "index.html").is_file():
    _index = Path(config.STATIC_DIR, "index.html")

    @app.get("/login", include_in_schema=False)
    @app.get("/register", include_in_schema=False)
    def legacy_auth_redirect():
        return RedirectResponse("/", status_code=307)

    @app.get("/app", include_in_schema=False)
    def spa_entry():
        return FileResponse(_index)

    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="ui")
