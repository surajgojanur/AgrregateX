"""Tenant analytics queries on ENGINE_CONTRACT v1.

Exact arbitrary windows [from, to): complete UTC buckets come from stream tables; the
partial edges (< one bucket) come from raw ax.orders via (tenant_id, created_at) index.
Edges and buckets are disjoint, so every order is counted exactly once.
Sales = status NOT IN ('cancelled','refunded') (PROPOSED semantics; confirm with organizer).
All money is integer cents.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
NOT_SALE = ("cancelled", "refunded")


@dataclass(frozen=True)
class Window:
    start: datetime          # aware UTC
    end: datetime            # aware UTC, exclusive
    full_lo: datetime        # naive UTC, first complete bucket
    full_hi: datetime        # naive UTC, exclusive
    edge1_end: datetime      # raw edge 1 = [start, edge1_end)
    edge2_start: datetime    # raw edge 2 = [edge2_start, end)

    def params(self, tenant_id: int) -> dict:
        return {"t": tenant_id, "f": self.start, "to": self.end, "flo": self.full_lo,
                "fhi": self.full_hi, "e1": self.edge1_end, "e2": self.edge2_start}


def _floor(dt: datetime, unit: str) -> datetime:
    dt = dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return dt.replace(hour=0) if unit == "day" else dt


def split(start: datetime, end: datetime, unit: str) -> Window:
    step = timedelta(days=1) if unit == "day" else timedelta(hours=1)
    lo = _floor(start, unit)
    if lo < start:
        lo += step
    hi = _floor(end, unit)
    naive = lambda d: d.astimezone(UTC).replace(tzinfo=None)  # noqa: E731
    if lo >= hi:  # no complete bucket: the whole range is one raw scan
        return Window(start, end, naive(lo), naive(lo), end, end)
    return Window(start, end, naive(lo), naive(hi), lo, hi)


RAW_EDGES = ("tenant_id = %(t)s AND ((created_at >= %(f)s AND created_at < %(e1)s)"
             " OR (created_at >= %(e2)s AND created_at < %(to)s))")
RAW_EDGES_O = ("o.tenant_id = %(t)s AND ((o.created_at >= %(f)s AND o.created_at < %(e1)s)"
               " OR (o.created_at >= %(e2)s AND o.created_at < %(to)s))")


def summary(conn, tenant_id: int, w: Window) -> dict:
    rows = conn.execute(f"""
        WITH s AS (
            SELECT status, sum(order_count) n, sum(units) u, sum(sales_cents) c
              FROM ax.st_day_product_status
             WHERE tenant_id = %(t)s AND utc_day >= %(flo)s AND utc_day < %(fhi)s GROUP BY status
            UNION ALL
            SELECT status, count(*), sum(quantity), sum(line_cents)
              FROM ax.orders WHERE {RAW_EDGES} GROUP BY status)
        SELECT status, sum(n)::bigint AS orders, COALESCE(sum(u), 0)::bigint AS units,
               COALESCE(sum(c), 0)::bigint AS cents
          FROM s GROUP BY status ORDER BY status""", w.params(tenant_id)).fetchall()
    by_status = {r["status"]: {"orders": r["orders"], "units": r["units"], "gross_cents": r["cents"]}
                 for r in rows}
    sales = [v for k, v in by_status.items() if k not in NOT_SALE]
    orders = sum(v["orders"] for v in by_status.values())
    sale_orders = sum(v["orders"] for v in sales)
    sales_cents = sum(v["gross_cents"] for v in sales)
    cancelled = by_status.get("cancelled", {}).get("orders", 0) + by_status.get("refunded", {}).get("orders", 0)
    return {
        "orders": orders,
        "sale_orders": sale_orders,
        "units_sold": sum(v["units"] for v in sales),
        "sales_cents": sales_cents,
        "avg_order_cents": (sales_cents // sale_orders) if sale_orders else 0,
        "cancelled_or_refunded": cancelled,
        "cancel_rate": round(cancelled / orders, 4) if orders else 0.0,
        "by_status": by_status,
    }


def trends(conn, tenant_id: int, w: Window, grain: str) -> list[dict]:
    st, col = ("ax.st_day_category_status", "utc_day") if grain == "day" else \
              ("ax.st_hour_category_status", "utc_hour")
    rows = conn.execute(f"""
        WITH s AS (
            SELECT {col} AS b, status, sum(order_count) n, sum(sales_cents) c FROM {st}
             WHERE tenant_id = %(t)s AND {col} >= %(flo)s AND {col} < %(fhi)s GROUP BY 1, 2
            UNION ALL
            SELECT {col}, status, count(*), sum(line_cents) FROM ax.orders WHERE {RAW_EDGES} GROUP BY 1, 2)
        SELECT b,
               sum(n)::bigint AS orders,
               COALESCE(sum(c) FILTER (WHERE status NOT IN ('cancelled','refunded')), 0)::bigint AS sales_cents,
               COALESCE(sum(n) FILTER (WHERE status IN ('cancelled','refunded')), 0)::bigint AS cancelled
          FROM s GROUP BY b ORDER BY b""", w.params(tenant_id)).fetchall()
    return [{"bucket": r["b"].replace(tzinfo=UTC).isoformat(), "orders": r["orders"],
             "sales_cents": r["sales_cents"], "cancelled_or_refunded": r["cancelled"]} for r in rows]


def top_products(conn, tenant_id: int, w: Window, limit: int) -> list[dict]:
    p = w.params(tenant_id) | {"lim": limit}
    rows = conn.execute(f"""
        WITH s AS (
            SELECT product_id, sum(sales_cents) c, sum(units) u, sum(order_count) n
              FROM ax.st_day_product_status
             WHERE tenant_id = %(t)s AND utc_day >= %(flo)s AND utc_day < %(fhi)s
               AND status NOT IN ('cancelled','refunded') GROUP BY 1
            UNION ALL
            SELECT product_id, sum(line_cents), sum(quantity), count(*) FROM ax.orders
             WHERE {RAW_EDGES} AND status NOT IN ('cancelled','refunded') GROUP BY 1),
        t AS (SELECT product_id, sum(c)::bigint AS cents, sum(u)::bigint AS units, sum(n)::bigint AS orders
                FROM s GROUP BY product_id)
        SELECT t.product_id, p.name, p.category_id, t.cents, t.units, t.orders
          FROM t LEFT JOIN ax.products p ON p.tenant_id = %(t)s AND p.product_id = t.product_id
         ORDER BY t.cents DESC, t.product_id ASC LIMIT %(lim)s""", p).fetchall()
    return [{"rank": i + 1, "product_id": r["product_id"], "name": r["name"], "category_id": r["category_id"],
             "sales_cents": r["cents"], "units_sold": r["units"], "orders": r["orders"]}
            for i, r in enumerate(rows)]


def breakdown(conn, tenant_id: int, w: Window, by: str) -> list[dict]:
    if by == "status":
        s = summary(conn, tenant_id, w)["by_status"]
        return [{"key": k, **v} for k, v in sorted(s.items())]
    rows = conn.execute(f"""
        WITH s AS (
            SELECT category_id, status, sum(order_count) n, sum(units) u, sum(sales_cents) c
              FROM ax.st_day_category_status
             WHERE tenant_id = %(t)s AND utc_day >= %(flo)s AND utc_day < %(fhi)s GROUP BY 1, 2
            UNION ALL
            SELECT p.category_id, o.status, count(*), sum(o.quantity), sum(o.line_cents)
              FROM ax.orders o JOIN ax.products p ON p.tenant_id = o.tenant_id AND p.product_id = o.product_id
             WHERE {RAW_EDGES_O}
             GROUP BY 1, 2)
        SELECT category_id AS key,
               sum(n)::bigint AS orders,
               COALESCE(sum(u) FILTER (WHERE status NOT IN ('cancelled','refunded')), 0)::bigint AS units,
               COALESCE(sum(c) FILTER (WHERE status NOT IN ('cancelled','refunded')), 0)::bigint AS sales_cents
          FROM s GROUP BY category_id ORDER BY sales_cents DESC, category_id""", w.params(tenant_id)).fetchall()
    return [dict(r) for r in rows]
