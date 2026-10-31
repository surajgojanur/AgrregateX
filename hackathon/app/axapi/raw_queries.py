"""Correctness-first analytics derived only from authoritative tenant source rows.

Each function executes one parameterized SQL statement. The caller must use
``db.tenant_tx('api', tenant_id)`` so routing and forced RLS remain in force.
"""

from datetime import UTC

from .queries import NOT_SALE, Window

SUMMARY_SQL = """
SELECT status,
       count(*)::bigint AS orders,
       coalesce(sum(quantity), 0)::bigint AS units,
       coalesce(sum(quantity::bigint * unit_price_cents), 0)::bigint AS gross_cents
  FROM ax.orders
 WHERE tenant_id = %(t)s AND created_at >= %(f)s AND created_at < %(to)s
 GROUP BY status ORDER BY status
"""

TREND_SQL = """SELECT {bucket} AS bucket,
       count(*)::bigint AS orders,
       coalesce(sum(quantity::bigint * unit_price_cents)
         FILTER (WHERE status NOT IN ('cancelled','refunded')), 0)::bigint AS sales_cents,
       count(*) FILTER (WHERE status IN ('cancelled','refunded'))::bigint AS cancelled_or_refunded
  FROM ax.orders
 WHERE tenant_id = %(t)s AND created_at >= %(f)s AND created_at < %(to)s
 GROUP BY 1 ORDER BY 1"""

TOP_PRODUCTS_SQL = """SELECT p.product_id, p.name, p.category_id,
       coalesce(sum(o.quantity::bigint * o.unit_price_cents), 0)::bigint AS sales_cents,
       coalesce(sum(o.quantity), 0)::bigint AS units_sold,
       count(*)::bigint AS orders
  FROM ax.orders o
  JOIN ax.products p ON p.tenant_id = o.tenant_id AND p.product_id = o.product_id
 WHERE o.tenant_id = %(t)s AND o.created_at >= %(f)s AND o.created_at < %(to)s
   AND o.status NOT IN ('cancelled','refunded')
 GROUP BY p.tenant_id, p.product_id, p.name, p.category_id
 ORDER BY sales_cents DESC, p.product_id ASC
 LIMIT %(lim)s"""

STATUS_BREAKDOWN_SQL = """SELECT status AS key,
       count(*)::bigint AS orders,
       coalesce(sum(quantity), 0)::bigint AS units,
       coalesce(sum(quantity::bigint * unit_price_cents), 0)::bigint AS gross_cents
  FROM ax.orders
 WHERE tenant_id = %(t)s AND created_at >= %(f)s AND created_at < %(to)s
 GROUP BY status ORDER BY status"""

CATEGORY_BREAKDOWN_SQL = """SELECT p.category_id AS key,
       count(*)::bigint AS orders,
       coalesce(sum(o.quantity) FILTER (WHERE o.status NOT IN ('cancelled','refunded')), 0)::bigint AS units,
       coalesce(sum(o.quantity::bigint * o.unit_price_cents)
         FILTER (WHERE o.status NOT IN ('cancelled','refunded')), 0)::bigint AS sales_cents
  FROM ax.orders o
  JOIN ax.products p ON p.tenant_id = o.tenant_id AND p.product_id = o.product_id
 WHERE o.tenant_id = %(t)s AND o.created_at >= %(f)s AND o.created_at < %(to)s
 GROUP BY p.tenant_id, p.category_id
 ORDER BY sales_cents DESC, p.category_id ASC"""


def _params(tenant_id: int, window: Window) -> dict:
    return {"t": int(tenant_id), "f": window.start, "to": window.end}


def _summary_from_rows(rows: list[dict]) -> dict:
    by_status = {
        row["status"]: {
            "orders": int(row["orders"]),
            "units": int(row["units"]),
            "gross_cents": int(row["gross_cents"]),
        }
        for row in rows
    }
    sales = [value for status, value in by_status.items() if status not in NOT_SALE]
    orders = sum(value["orders"] for value in by_status.values())
    sale_orders = sum(value["orders"] for value in sales)
    sales_cents = sum(value["gross_cents"] for value in sales)
    cancelled = sum(by_status.get(status, {}).get("orders", 0) for status in NOT_SALE)
    return {
        "orders": orders,
        "sale_orders": sale_orders,
        "units_sold": sum(value["units"] for value in sales),
        "sales_cents": sales_cents,
        "avg_order_cents": sales_cents // sale_orders if sale_orders else 0,
        "cancelled_or_refunded": cancelled,
        "cancel_rate": round(cancelled / orders, 4) if orders else 0.0,
        "by_status": by_status,
    }


def summary(conn, tenant_id: int, window: Window) -> dict:
    rows = conn.execute(SUMMARY_SQL, _params(tenant_id, window)).fetchall()
    return _summary_from_rows(rows)


def trends(conn, tenant_id: int, window: Window, grain: str) -> list[dict]:
    buckets = {
        "day": "date_trunc('day', created_at AT TIME ZONE 'UTC')",
        "hour": "date_trunc('hour', created_at AT TIME ZONE 'UTC')",
    }
    if grain not in buckets:
        raise ValueError("grain must be 'day' or 'hour'")
    rows = conn.execute(
        TREND_SQL.format(bucket=buckets[grain]), _params(tenant_id, window)
    ).fetchall()
    return [
        {
            "bucket": row["bucket"].replace(tzinfo=UTC).isoformat(),
            "orders": int(row["orders"]),
            "sales_cents": int(row["sales_cents"]),
            "cancelled_or_refunded": int(row["cancelled_or_refunded"]),
        }
        for row in rows
    ]


def top_products(conn, tenant_id: int, window: Window, limit: int) -> list[dict]:
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    rows = conn.execute(
        TOP_PRODUCTS_SQL, _params(tenant_id, window) | {"lim": limit}
    ).fetchall()
    return [
        {
            "rank": index,
            "product_id": row["product_id"],
            "name": row["name"],
            "category_id": row["category_id"],
            "sales_cents": int(row["sales_cents"]),
            "units_sold": int(row["units_sold"]),
            "orders": int(row["orders"]),
        }
        for index, row in enumerate(rows, 1)
    ]


def breakdown(conn, tenant_id: int, window: Window, by: str) -> list[dict]:
    if by == "status":
        rows = conn.execute(STATUS_BREAKDOWN_SQL, _params(tenant_id, window)).fetchall()
        return [
            {
                "key": row["key"],
                "orders": int(row["orders"]),
                "units": int(row["units"]),
                "gross_cents": int(row["gross_cents"]),
            }
            for row in rows
        ]
    if by == "category":
        rows = conn.execute(
            CATEGORY_BREAKDOWN_SQL, _params(tenant_id, window)
        ).fetchall()
        return [
            {key: int(value) if key != "key" else value for key, value in row.items()}
            for row in rows
        ]
    raise ValueError("by must be 'status' or 'category'")
