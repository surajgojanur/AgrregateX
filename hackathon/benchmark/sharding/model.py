"""Pure testable contracts for two-shard routing; no network or DB calls."""
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
        raise AssertionError("each expected tenant must have exactly one mapping")
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

def aggregates(rows: Sequence[Order]):
    result = {}
    for r in rows:
        key = (r.tenant_id, r.day, r.product_id, r.category_id, r.status)
        state = result.setdefault(key, [0, 0, 0])
        state[0] += 1
        state[1] += r.quantity
        state[2] += r.quantity * r.unit_price_cents
    return {k: tuple(v) for k, v in result.items()}

def compare_shards(mapping, shard_rows, tenants, shards):
    validate_mapping(mapping, shards, tenants)
    seen = {}
    for shard in shards:
        for row in shard_rows.get(shard, ()):
            if row.tenant_id in seen and seen[row.tenant_id] != shard:
                raise AssertionError(f"tenant {row.tenant_id} duplicated across shards")
            seen[row.tenant_id] = shard
            if mapping[row.tenant_id] != shard:
                raise AssertionError(f"tenant {row.tenant_id} stored on wrong shard")
    if set(seen) != set(tenants):
        raise AssertionError("tenant rows missing from shard set")
    return {s: aggregates(shard_rows.get(s, ())) for s in shards}
