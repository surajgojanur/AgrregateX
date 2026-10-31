"""Background OLTP-style writer so the dashboard shows live data (demo only).

Writes AX_WRITER_RATE changes/second (default 5) as ax_writer under RLS, one tenant per
transaction: ~65 % new orders, ~20 % cancellations, ~15 % shipments. Kept deliberately low:
see handoff F3 (refresh cost per changed group) before raising it.
"""
import os
import random
import time

from . import db

RATE = float(os.environ.get("AX_WRITER_RATE", "5"))
TENANTS = int(os.environ.get("AX_DEMO_TENANTS", "10"))
WEIGHTS = [0.4, 0.2] + [0.4 / max(TENANTS - 2, 1)] * max(TENANTS - 2, 0)


def step() -> None:
    t = random.choices(range(1, TENANTS + 1), weights=WEIGHTS[:TENANTS])[0]
    op = random.random()
    with db.tenant_tx(db.writer_pool, t) as c:
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


def main() -> None:
    db.writer_pool.open(wait=True, timeout=120)
    interval = 1.0 / RATE if RATE > 0 else 1.0
    print(f"aggregatex writer: {RATE} changes/s across {TENANTS} tenants", flush=True)
    while True:
        started = time.monotonic()
        try:
            step()
        except Exception as exc:  # noqa: BLE001 - keep the demo writer alive across DB restarts
            print(f"writer error: {exc}".splitlines()[0], flush=True)
            time.sleep(2)
        time.sleep(max(0.0, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
