"""Background OLTP-style writer so the dashboard shows live data (demo only).

Writes AX_WRITER_RATE changes/second (default 2) as ax_writer under RLS, one tenant per
transaction, ALWAYS on the tenant's owning shard: ~65 % new orders, ~20 % cancellations,
~15 % shipments. If the owning shard is unreachable the change is skipped and counted. It is
never redirected to another shard. Rate is kept low on purpose (handoff F3).
"""
import os
import random
import time
from collections import Counter

from . import db

RATE = float(os.environ.get("AX_WRITER_RATE", "2"))
_TENANTS = sorted(db.DIRECTORY) or list(range(1, int(os.environ.get("AX_DEMO_TENANTS", "10")) + 1))
# Same skew as the seed: tenant 1 = 40 %, tenant 2 = 20 %, the rest share 40 %.
_WEIGHTS = [0.4 if t == 1 else 0.2 if t == 2 else 0.4 / max(len(_TENANTS) - 2, 1) for t in _TENANTS]
stats: Counter = Counter()


def step() -> None:
    t = random.choices(_TENANTS, weights=_WEIGHTS)[0]
    op = random.random()
    with db.tenant_tx("writer", t) as c:
        if op < 0.65:
            c.execute("""INSERT INTO ax.orders (tenant_id, order_id, customer_id, product_id, status, quantity,
                                                unit_price_cents, created_at)
                         VALUES (%s, nextval('ax.order_id_seq'), %s, %s, 'paid', %s, %s, now())""",
                      (t, random.randint(1, 1000), 1 + int(random.random() ** 2 * 200),
                       random.randint(1, 5), random.randint(100, 99999)))
        else:
            new = "cancelled" if op < 0.85 else "shipped"
            c.execute("""UPDATE ax.orders SET status = %s, updated_at = now()
                          WHERE tenant_id = %s AND order_id = (
                                SELECT order_id FROM ax.orders WHERE tenant_id = %s AND status = 'paid'
                                 ORDER BY created_at DESC OFFSET %s LIMIT 1)""",
                      (new, t, t, random.randint(0, 50)))
    stats[f"ok:{db.shard_for(t).name}"] += 1


def main() -> None:
    db.open_all()
    interval = 1.0 / RATE if RATE > 0 else 1.0
    print(f"aggregatex writer: {RATE} changes/s, tenants {_TENANTS}, shards {list(db.SHARDS)}", flush=True)
    last_report = time.monotonic()
    while True:
        started = time.monotonic()
        try:
            step()
        except db.ShardUnavailable as exc:
            stats[f"skipped:{exc.shard}"] += 1   # fail closed: no cross-shard fallback
        except Exception as exc:  # noqa: BLE001 - keep the demo writer alive
            stats["error"] += 1
            print(f"writer error: {exc}".splitlines()[0], flush=True)
        if time.monotonic() - last_report > 30:
            print(f"writer stats: {dict(stats)}", flush=True)
            last_report = time.monotonic()
        time.sleep(max(0.0, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
