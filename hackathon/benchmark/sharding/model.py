"""Pure testable contracts for two-shard routing and three stream-table grains."""
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

class ShardUnavailable(Exception):
    pass

class ServiceUnavailable(Exception):
    status_code = 503

@dataclass(frozen=True)
class Order:
    tenant_id: int
    order_id: int
    day: str
    hour: str
    product_id: int | None
    category_id: int | None
    status: str
    quantity: int
    unit_price_cents: int

def validate_mapping(mapping: Mapping[int, str], shards: Sequence[str], expected_tenants: Sequence[int]) -> None:
    if len(set(shards)) != len(shards) or not shards:
        raise AssertionError("shard names must be non-empty and unique")
    if set(mapping) != set(expected_tenants):
        raise AssertionError("every directory tenant must map to exactly one shard")
    if any(mapping[t] not in shards for t in expected_tenants):
        raise AssertionError("tenant mapped to unknown shard")

def route(tenant_id: int, mapping: Mapping[int, str], clients: Mapping[str, Callable]):
    try:
        client = clients[mapping[tenant_id]]
    except KeyError as exc:
        raise ServiceUnavailable("tenant shard is not configured") from exc
    try:
        return client(tenant_id)
    except ShardUnavailable as exc:
        raise ServiceUnavailable(f"tenant {tenant_id} shard unavailable") from exc

def oracle_streams(rows: Sequence[Order]):
    """Independent in-memory truth for exact stream-table group keys."""
    specs = {
        "st_day_product_status": lambda r: (r.tenant_id, r.day, r.product_id, r.status),
        "st_day_category_status": lambda r: (r.tenant_id, r.day, r.category_id, r.status),
        "st_hour_category_status": lambda r: (r.tenant_id, r.hour, r.category_id, r.status),
    }
    results = {}
    for name, key_fn in specs.items():
        groups = {}
        for row in rows:
            key = key_fn(row)
            acc = groups.setdefault(key, [0, 0, 0])
            acc[0] += 1
            acc[1] += row.quantity
            acc[2] += row.quantity * row.unit_price_cents
        results[name] = {key: tuple(values) for key, values in groups.items()}
    return results

def multiset_mismatches(expected, actual):
    """Both directions; maps represent unique SQL GROUP BY keys, values aggregate tuples."""
    missing = {k: v for k, v in expected.items() if actual.get(k) != v}
    extra = {k: v for k, v in actual.items() if expected.get(k) != v}
    return missing, extra

def compare_shards(mapping, shard_rows, tenants, shards):
    """Directory completeness is separate; mapped tenants may have zero source rows."""
    validate_mapping(mapping, shards, tenants)
    seen = {}
    for shard in shards:
        for row in shard_rows.get(shard, ()):
            if row.tenant_id in seen and seen[row.tenant_id] != shard:
                raise AssertionError(f"tenant {row.tenant_id} duplicated across shards")
            seen[row.tenant_id] = shard
            if row.tenant_id not in mapping or mapping[row.tenant_id] != shard:
                raise AssertionError(f"tenant {row.tenant_id} stored on wrong shard")
    return {s: oracle_streams(shard_rows.get(s, ())) for s in shards}
