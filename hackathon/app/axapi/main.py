"""AgrregateX API: tenant-safe analytics over pg_trickle stream tables (+ built UI)."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config, db, engine, queries

UTC = timezone.utc


@asynccontextmanager
async def lifespan(_app):
    db.open_all()
    yield
    db.close_all()


app = FastAPI(title="AgrregateX API", version=config.VERSION, lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")


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


def _meta(tenant_id: int, start: datetime, end: datetime, w: queries.Window, **extra) -> dict:
    has_full = w.full_lo < w.full_hi
    edges = [[start.isoformat(), w.edge1_end.isoformat()]] if start < w.edge1_end else []
    if w.edge2_start < end and has_full:
        edges.append([w.edge2_start.isoformat(), end.isoformat()])
    return {"tenant_id": tenant_id, "from": start.isoformat(), "to": end.isoformat(),
            "source": {"stream_table_range": [w.full_lo.replace(tzinfo=UTC).isoformat(),
                                              w.full_hi.replace(tzinfo=UTC).isoformat()] if has_full else None,
                       "raw_edge_ranges": edges},
            **extra}


def _run(fn, tenant_id, *args):
    with db.tenant_tx(db.api_pool, tenant_id) as conn:
        return fn(conn, tenant_id, *args)


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
    try:
        with db.monitor_pool.connection(timeout=2) as c:
            v = c.execute("SELECT extversion FROM pg_extension WHERE extname = 'pg_trickle'").fetchone()
        return {"status": "ok", "version": config.VERSION, "database": "ok",
                "pg_trickle_version": v["extversion"] if v else None}
    except Exception:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "version": config.VERSION, "database": "unreachable"},
                            status_code=503)


@app.get("/api/tenants")
def tenants(user: auth.User = Depends(auth.current_user)):
    with db.monitor_pool.connection() as c:
        rows = c.execute("SELECT tenant_id, name FROM ax.tenants WHERE tenant_id < 999 ORDER BY tenant_id").fetchall()
    return {"tenants": [r for r in rows if user.can_read_tenant(r["tenant_id"])]}


# ── tenant analytics ───────────────────────────────────────────────────────
def tenant_path(tenant_id: int, user: auth.User = Depends(auth.current_user)) -> int:
    return auth.authorize_tenant(user, tenant_id)


@app.get("/api/tenants/{tenant_id}/summary")
async def summary(tenant_id: int = Depends(tenant_path), win=Depends(window)):
    w = queries.split(*win, "day")
    data = await run_in_threadpool(_run, queries.summary, tenant_id, w)
    return _meta(tenant_id, *win, w, summary=data)


@app.get("/api/tenants/{tenant_id}/trends")
async def trends(tenant_id: int = Depends(tenant_path), win=Depends(window),
                 grain: Literal["day", "hour"] = "day"):
    if grain == "hour" and win[1] - win[0] > timedelta(days=config.MAX_HOURLY_RANGE_DAYS):
        raise HTTPException(422, f"Hourly trends are limited to {config.MAX_HOURLY_RANGE_DAYS} days.")
    w = queries.split(*win, grain)
    data = await run_in_threadpool(_run, queries.trends, tenant_id, w, grain)
    return _meta(tenant_id, *win, w, grain=grain, points=data)


@app.get("/api/tenants/{tenant_id}/top-products")
async def top_products(tenant_id: int = Depends(tenant_path), win=Depends(window),
                       limit: int = Query(10, ge=1, le=50)):
    w = queries.split(*win, "day")
    data = await run_in_threadpool(_run, queries.top_products, tenant_id, w, limit)
    return _meta(tenant_id, *win, w, limit=limit, products=data)


@app.get("/api/tenants/{tenant_id}/breakdown")
async def breakdown(tenant_id: int = Depends(tenant_path), win=Depends(window),
                    by: Literal["status", "category"] = "status"):
    w = queries.split(*win, "day")
    data = await run_in_threadpool(_run, queries.breakdown, tenant_id, w, by)
    return _meta(tenant_id, *win, w, by=by, rows=data)


@app.get("/api/tenants/{tenant_id}/freshness")
async def freshness(tenant_id: int = Depends(tenant_path)):
    return {"tenant_id": tenant_id, **await run_in_threadpool(engine.freshness)}


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
async def engine_snapshot(_admin: auth.User = Depends(auth.require_admin)):
    return await run_in_threadpool(engine.snapshot)


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_not_found(rest: str):
    raise HTTPException(404, "Not found.")


# ── built frontend (single-port demo) ──────────────────────────────────────
if config.STATIC_DIR and Path(config.STATIC_DIR, "index.html").is_file():
    _index = Path(config.STATIC_DIR, "index.html")

    @app.get("/app", include_in_schema=False)
    @app.get("/login", include_in_schema=False)
    @app.get("/register", include_in_schema=False)
    def spa_entry():
        return FileResponse(_index)

    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="ui")
