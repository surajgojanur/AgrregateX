"""B-4: config-driven metrics, derived from the EXISTING pg_trickle stream tables.

Adding a metric means editing ONE JSON file (``AX_METRICS_CONFIG``, default ``app/config/metrics.json``).
There is no code change and no restart: the file is re-read when its mtime/size changes.

What a config can express (everything else is rejected at load time):
  * ``type``: ``sum`` (one measure) or ``ratio`` (numerator / denominator).
  * a measure is one allow-listed field ID (``orders``, ``units``, ``gross_cents``) and an allow-listed status filter
    (``all``, ``sale``, ``not_sale`` or a list of known statuses).
  * ``group_by``: allow-listed groupings, each backed by a stream table that already exists.

What it cannot express: SQL, column/table/function names, expressions, new materialisations. The config is
**data**. It picks from fixed tables in this module and never reaches the SQL text. Every SQL statement below is a
constant, chosen by grouping ID and executed with bound parameters.

These are DERIVED metrics over existing rollups, not new summaries. A metric that would need a rollup that does not
exist (for example by customer, or distinct customers) is rejected, with a message saying so.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .queries import NOT_SALE, Window

UTC = timezone.utc
log = logging.getLogger("axapi.metrics")

SCHEMA = "aggregatex.metrics/v1"
STATUSES = ("pending", "paid", "shipped", "cancelled", "refunded")   # = CHECK constraint on ax.orders.status
STATUS_SETS = {"all": STATUSES,
               "sale": tuple(s for s in STATUSES if s not in NOT_SALE),
               "not_sale": NOT_SALE}
MEASURES = {"orders": "order count", "units": "units (quantity)", "gross_cents": "line value in cents"}
UNITS = ("count", "cents", "units", "ratio", "percent")
SCALES = (1, 100)
MAX_METRICS = 32
MAX_CONFIG_BYTES = 64 * 1024
ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")

# Fields the config may NOT ask for, with the reason. This makes "unsupported rollup" an explicit, clear rejection.
UNSUPPORTED = {
    "customer": "no stream table is grouped by customer",
    "customer_id": "no stream table is grouped by customer",
    "region": "no stream table is grouped by region",
    "distinct_customers": "distinct counts are not derivable from the existing rollups",
    "unit_price_cents": "no rollup stores prices; use gross_cents / units instead",
}


# ── fixed SQL (never built from config) ──────────────────────────────────────
@dataclass(frozen=True)
class Grouping:
    stream_table: str       # existing rollup that serves complete buckets
    bucket_col: str         # utc_day or utc_hour on that rollup
    unit: str               # "day"/"hour": window split for exact edges
    st_key: str             # key expression on the stream table
    raw_key: str            # same key over ax.orders o (rollup edges)
    raw_src_key: str        # same key in raw_source mode
    needs_products: bool    # raw branch joins ax.products (category key)
    key_kind: str           # how keys are serialised


GROUPINGS = {
    "total":    Grouping("ax.st_day_product_status", "utc_day", "day", "'total'", "'total'", "'total'", False, "text"),
    "status":   Grouping("ax.st_day_product_status", "utc_day", "day", "status", "o.status", "o.status", False, "text"),
    "product":  Grouping("ax.st_day_product_status", "utc_day", "day", "product_id", "o.product_id", "o.product_id",
                         False, "int"),
    "category": Grouping("ax.st_day_category_status", "utc_day", "day", "category_id", "p.category_id",
                         "p.category_id", True, "int"),
    "day":      Grouping("ax.st_day_category_status", "utc_day", "day", "utc_day", "o.utc_day",
                         "date_trunc('day', o.created_at AT TIME ZONE 'UTC')", False, "time"),
    "hour":     Grouping("ax.st_hour_category_status", "utc_hour", "hour", "utc_hour", "o.utc_hour",
                         "date_trunc('hour', o.created_at AT TIME ZONE 'UTC')", False, "time"),
}
_JOIN = "JOIN ax.products p ON p.tenant_id = o.tenant_id AND p.product_id = o.product_id"
_EDGES = ("o.tenant_id = %(t)s AND ((o.created_at >= %(f)s AND o.created_at < %(e1)s)"
          " OR (o.created_at >= %(e2)s AND o.created_at < %(to)s))")


def _rollup_sql(g: Grouping) -> str:
    return f"""
        WITH s AS (
            SELECT {g.st_key} AS k, status, sum(order_count) n, sum(units) u, sum(sales_cents) c
              FROM {g.stream_table}
             WHERE tenant_id = %(t)s AND {g.bucket_col} >= %(flo)s AND {g.bucket_col} < %(fhi)s GROUP BY 1, 2
            UNION ALL
            SELECT {g.raw_key}, o.status, count(*), sum(o.quantity), sum(o.line_cents)
              FROM ax.orders o {_JOIN if g.needs_products else ""}
             WHERE {_EDGES} GROUP BY 1, 2)
        SELECT k, status, sum(n)::bigint AS orders, COALESCE(sum(u), 0)::bigint AS units,
               COALESCE(sum(c), 0)::bigint AS gross_cents
          FROM s GROUP BY 1, 2"""


def _raw_sql(g: Grouping) -> str:
    return f"""
        SELECT {g.raw_src_key} AS k, o.status, count(*)::bigint AS orders,
               COALESCE(sum(o.quantity), 0)::bigint AS units,
               COALESCE(sum(o.quantity::bigint * o.unit_price_cents), 0)::bigint AS gross_cents
          FROM ax.orders o {_JOIN if g.needs_products else ""}
         WHERE o.tenant_id = %(t)s AND o.created_at >= %(f)s AND o.created_at < %(to)s
         GROUP BY 1, 2"""


SQL = {name: {"rollup": _rollup_sql(g), "raw_source": _raw_sql(g)} for name, g in GROUPINGS.items()}


def source_tables(group_by: str, mode: str) -> list[str]:
    g = GROUPINGS[group_by]
    tables = ["ax.orders"] + (["ax.products"] if g.needs_products else [])
    return tables if mode == "raw_source" else [g.stream_table, *tables]


# ── config model + validation ────────────────────────────────────────────────
class ConfigError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Measure:
    field: str
    statuses: tuple[str, ...]
    status_label: str

    def public(self) -> dict:
        return {"measure": self.field, "statuses": self.status_label, "resolved_statuses": list(self.statuses)}


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    description: str
    unit: str
    type: str
    numerator: Measure
    denominator: Measure | None
    scale: int
    decimals: int
    group_by: tuple[str, ...]

    def public(self) -> dict:
        return {"id": self.id, "label": self.label, "description": self.description, "unit": self.unit,
                "type": self.type, "numerator": self.numerator.public(),
                "denominator": self.denominator.public() if self.denominator else None,
                "scale": self.scale, "decimals": self.decimals, "group_by": list(self.group_by),
                "derived_from": sorted({GROUPINGS[g].stream_table for g in self.group_by})}


@dataclass(frozen=True)
class Registry:
    version: int
    metrics: dict[str, Metric]


def _keys(obj: dict, where: str, required: set[str], optional: set[str], errs: list[str]) -> bool:
    if not isinstance(obj, dict):
        errs.append(f"{where}: must be an object")
        return False
    for k in sorted(set(obj) - required - optional):
        hint = f" ({UNSUPPORTED[k]})" if k in UNSUPPORTED else ""
        errs.append(f"{where}: unknown key {k!r}{hint}")
    for k in sorted(required - set(obj)):
        errs.append(f"{where}: missing required key {k!r}")
    return True


def _measure(raw, where: str, errs: list[str]) -> Measure | None:
    if not _keys(raw, where, {"measure"}, {"statuses"}, errs):
        return None
    field = raw.get("measure")
    if field not in MEASURES:
        why = UNSUPPORTED.get(field) if isinstance(field, str) else None
        errs.append(f"{where}.measure: {field!r} is not an allowed field "
                    f"({why or 'allowed: ' + ', '.join(MEASURES)})")
        return None
    st = raw.get("statuses", "all")
    if isinstance(st, str):
        if st not in STATUS_SETS:
            errs.append(f"{where}.statuses: {st!r} is not one of {', '.join(STATUS_SETS)} or a list of statuses")
            return None
        return Measure(field, STATUS_SETS[st], st)
    if not isinstance(st, list) or not st or not all(isinstance(s, str) for s in st):
        errs.append(f"{where}.statuses: must be a set name or a non-empty list of statuses")
        return None
    bad = [s for s in st if s not in STATUSES]
    if bad or len(set(st)) != len(st):
        errs.append(f"{where}.statuses: unknown or duplicate status in {st!r} (allowed: {', '.join(STATUSES)})")
        return None
    return Measure(field, tuple(s for s in STATUSES if s in st), ",".join(s for s in STATUSES if s in st))


def _metric(raw, i: int, errs: list[str]) -> Metric | None:
    where = f"metrics[{i}]"
    n0 = len(errs)
    if not _keys(raw, where, {"id", "label", "type", "unit", "numerator", "group_by"},
                 {"description", "denominator", "scale", "decimals"}, errs):
        return None
    mid = raw.get("id")
    if not isinstance(mid, str) or not ID_RE.match(mid):
        errs.append(f"{where}.id: must match {ID_RE.pattern}")
    else:
        where = f"metric {mid!r}"
    label, desc = raw.get("label"), raw.get("description", "")
    if not isinstance(label, str) or not 1 <= len(label) <= 60:
        errs.append(f"{where}.label: text of 1-60 characters")
    if not isinstance(desc, str) or len(desc) > 240:
        errs.append(f"{where}.description: text of at most 240 characters")
    mtype, unit = raw.get("type"), raw.get("unit")
    if mtype not in ("sum", "ratio"):
        errs.append(f"{where}.type: {mtype!r} is not 'sum' or 'ratio'")
    if unit not in UNITS:
        errs.append(f"{where}.unit: {unit!r} is not one of {', '.join(UNITS)}")
    num = _measure(raw.get("numerator"), f"{where}.numerator", errs)
    den = None
    if mtype == "ratio":
        if "denominator" not in raw:
            errs.append(f"{where}: a 'ratio' metric needs a denominator")
        else:
            den = _measure(raw["denominator"], f"{where}.denominator", errs)
    elif "denominator" in raw:
        errs.append(f"{where}: a 'sum' metric must not have a denominator")
    scale, decimals = raw.get("scale", 1), raw.get("decimals", 0)
    if type(scale) is not int or scale not in SCALES:
        errs.append(f"{where}.scale: must be one of {SCALES}")
    elif mtype == "sum" and scale != 1:
        errs.append(f"{where}.scale: a 'sum' metric must use scale 1")
    if type(decimals) is not int or not 0 <= decimals <= 4:
        errs.append(f"{where}.decimals: an integer from 0 to 4")
    gb = raw.get("group_by")
    if not isinstance(gb, list) or not gb or not all(isinstance(g, str) for g in gb) or len(set(gb)) != len(gb):
        errs.append(f"{where}.group_by: a non-empty list of distinct groupings")
    else:
        for g in gb:
            if g not in GROUPINGS:
                why = UNSUPPORTED.get(g, "allowed: " + ", ".join(GROUPINGS))
                errs.append(f"{where}.group_by: {g!r} needs a rollup that does not exist ({why})")
    if len(errs) > n0:
        return None
    return Metric(mid, label, desc, unit, mtype, num, den, scale, decimals, tuple(gb))


def parse(text: str) -> Registry:
    """Validate a whole config. Any error rejects the whole file (no partial registries)."""
    if len(text.encode()) > MAX_CONFIG_BYTES:
        raise ConfigError([f"config is larger than {MAX_CONFIG_BYTES} bytes"])
    try:
        doc = json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(f"{c} not allowed")))
    except ValueError as exc:
        raise ConfigError([f"not valid JSON: {exc}"]) from None
    errs: list[str] = []
    if not _keys(doc, "config", {"schema", "version", "metrics"}, set(), errs):
        raise ConfigError(errs)
    if doc.get("schema") != SCHEMA:
        errs.append(f"config.schema: must be {SCHEMA!r}")
    version = doc.get("version")
    if type(version) is not int or version < 1:
        errs.append("config.version: a positive integer")
    items = doc.get("metrics")
    metrics: dict[str, Metric] = {}
    if not isinstance(items, list) or not items:
        errs.append("config.metrics: a non-empty list")
    elif len(items) > MAX_METRICS:
        errs.append(f"config.metrics: at most {MAX_METRICS} metrics")
    else:
        for i, raw in enumerate(items):
            m = _metric(raw, i, errs)
            if m is None:
                continue
            if m.id in metrics:
                errs.append(f"metric {m.id!r}: duplicate id")
            metrics[m.id] = m
    if errs:
        raise ConfigError(errs)
    return Registry(version, metrics)


# ── hot-reloading file holder ────────────────────────────────────────────────
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "metrics.json"


class RegistryFile:
    """Holds the registry for one config path. It re-reads the file when its mtime or size changes, so an edit
    takes effect on the next request. An invalid file disables ALL metrics (fail closed: no stale or partial
    registry) and returns the validation errors until it is fixed."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._stamp: tuple | None = None
        self._registry: Registry | None = None
        self._errors: list[str] = []
        self.loads = 0

    def _stat(self) -> tuple | None:
        try:
            st = self.path.stat()
            return (st.st_mtime_ns, st.st_size, st.st_ino)
        except OSError:
            return None

    def get(self) -> Registry:
        stamp = self._stat()
        with self._lock:
            if stamp != self._stamp or (self._registry is None and not self._errors):
                self._stamp = stamp
                self.loads += 1
                try:
                    if stamp is None:
                        raise ConfigError([f"config file {self.path.name!r} is missing or unreadable"])
                    self._registry, self._errors = parse(self.path.read_text(encoding="utf-8")), []
                    log.info("metric registry v%s loaded: %d metrics", self._registry.version,
                             len(self._registry.metrics))
                except ConfigError as exc:
                    self._registry, self._errors = None, exc.errors
                    log.error("metric registry rejected: %s", exc)
                except OSError as exc:
                    self._registry, self._errors = None, [f"cannot read config: {exc.strerror}"]
            if self._registry is None:
                raise ConfigError(list(self._errors))
            return self._registry


REGISTRY = RegistryFile(os.environ.get("AX_METRICS_CONFIG") or DEFAULT_PATH)


# ── evaluation ───────────────────────────────────────────────────────────────
def fetch(conn, tenant_id: int, w: Window, group_by: str, mode: str) -> list[dict]:
    """One constant SQL statement for the grouping: rows (k, status, orders, units, gross_cents)."""
    return conn.execute(SQL[group_by][mode], w.params(tenant_id)).fetchall()


def _key(value, kind: str):
    if kind == "time":
        return value.replace(tzinfo=UTC).isoformat()
    return value


def _value(m: Metric, num: int, den: int | None):
    if m.type == "sum":
        return num, None
    if not den:
        return None, "denominator_zero"
    q = Decimal(1).scaleb(-m.decimals)
    v = (Decimal(num) * m.scale / Decimal(den)).quantize(q, rounding=ROUND_HALF_UP)
    return (int(v) if m.decimals == 0 else float(v)), None


def _component(rows: list[dict], measure: Measure) -> int:
    return sum(int(r[measure.field]) for r in rows if r["status"] in measure.statuses)


def evaluate(m: Metric, rows: list[dict], group_by: str, limit: int) -> dict:
    """Apply the metric to the per-(key, status) rows. Returns the total over the window plus one row per key."""
    kind = GROUPINGS[group_by].key_kind
    by_key: dict = {}
    for r in rows:
        by_key.setdefault(r["k"], []).append(r)

    def point(rs):
        num = _component(rs, m.numerator)
        den = _component(rs, m.denominator) if m.denominator else None
        value, why = _value(m, num, den)
        out = {"numerator": num, "denominator": den, "value": value}
        if why:
            out["undefined_reason"] = why
        return out

    total = point(rows)
    points = [{"key": _key(k, kind) if k is not None else None, **point(rs)} for k, rs in by_key.items()]
    if kind == "time":
        points.sort(key=lambda p: p["key"])
    elif group_by == "status":
        points.sort(key=lambda p: STATUSES.index(p["key"]))
    else:   # rank: defined values first, high to low; ties by key
        points.sort(key=lambda p: (p["value"] is None, -(p["value"] or 0), p["key"]))
    truncated = group_by == "product" and len(points) > limit
    return {"total": total, "rows": points[:limit] if group_by == "product" else points,
            "row_count": len(points), "truncated": truncated}
