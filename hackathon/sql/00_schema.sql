-- AgrregateX ENGINE_CONTRACT v1 — REPRESENTATIVE source schema (shared-DB topology).
-- NOT the organizer schema (not yet received). Column names are the contract the
-- stream tables depend on; adapt via a view/rename if the organizer schema differs.
--
-- Currency: integer minor units (cents, BIGINT). Never FLOAT.
-- Time:     created_at is TIMESTAMPTZ; all bucketing is UTC.
-- Status:   'pending' | 'paid' | 'shipped' | 'cancelled' | 'refunded'.
--           "Sales" metrics in the API = status NOT IN ('cancelled','refunded'),
--           computed at read time from per-status rows (stream tables keep every status).

CREATE SCHEMA IF NOT EXISTS ax;

CREATE TABLE IF NOT EXISTS ax.tenants (
    tenant_id   integer PRIMARY KEY,
    name        text NOT NULL
);

CREATE TABLE IF NOT EXISTS ax.products (
    tenant_id   integer NOT NULL REFERENCES ax.tenants,
    product_id  integer NOT NULL,
    category_id integer NOT NULL,
    name        text    NOT NULL,
    PRIMARY KEY (tenant_id, product_id)
);

CREATE TABLE IF NOT EXISTS ax.customers (
    tenant_id   integer NOT NULL REFERENCES ax.tenants,
    customer_id integer NOT NULL,
    name        text    NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE IF NOT EXISTS ax.orders (
    tenant_id        integer     NOT NULL,
    order_id         bigint      NOT NULL,
    customer_id      integer     NOT NULL,
    product_id       integer     NOT NULL,
    status           text        NOT NULL
        CHECK (status IN ('pending','paid','shipped','cancelled','refunded')),
    quantity         integer     NOT NULL CHECK (quantity > 0),
    unit_price_cents bigint      NOT NULL CHECK (unit_price_cents >= 0),
    created_at       timestamptz NOT NULL,
    updated_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, product_id)  REFERENCES ax.products,
    FOREIGN KEY (tenant_id, customer_id) REFERENCES ax.customers
);

-- Exact partial-bucket edge scans (range edges smaller than one hour).
CREATE INDEX IF NOT EXISTS orders_tenant_created_idx
    ON ax.orders (tenant_id, created_at);
