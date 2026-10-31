"""Connection pools, one per database role, and the tenant-scoped transaction helper."""
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

# ax_api: tenant reads (RLS). ax_writer: tenant writes (RLS). ax_monitor: engine catalog only.
api_pool = ConnectionPool(config.dsn("ax_api", config.API_PASSWORD), min_size=1, max_size=10,
                          open=False, kwargs={"row_factory": dict_row}, name="ax_api")
writer_pool = ConnectionPool(config.dsn("ax_writer", config.WRITER_PASSWORD), min_size=0, max_size=4,
                             open=False, kwargs={"row_factory": dict_row}, name="ax_writer")
monitor_pool = ConnectionPool(config.dsn("ax_monitor", config.MONITOR_PASSWORD), min_size=1, max_size=4,
                              open=False, kwargs={"row_factory": dict_row, "autocommit": True},
                              name="ax_monitor")
POOLS = (api_pool, writer_pool, monitor_pool)


def open_all() -> None:
    for pool in POOLS:
        pool.open(wait=False)


def close_all() -> None:
    for pool in POOLS:
        pool.close()


@contextmanager
def tenant_tx(pool: ConnectionPool, tenant_id: int):
    """One transaction with ax.tenant_id set LOCAL to a verified tenant id.

    The setting dies with the transaction, so pooled connections never leak a tenant.
    Without it, RLS policies compare against NULL and return no rows (fail closed).
    """
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('ax.tenant_id', %s, true)", (str(int(tenant_id)),))
            yield conn
