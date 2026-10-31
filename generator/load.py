#!/usr/bin/env python3
"""Compatibility wrapper for the Phase 00 command line `load.py ROWS TENANTS`.

The Phase 00 single-transaction loader was replaced in Phase 01A by the
resumable loader in generator/loader.py (see docs/LOADER_DESIGN.md). This
wrapper keeps `scripts/verify.sh` and README commands working:

  load.py 1000000 10    -> loader.py load --rows 1000000 --tenants 10
  load.py 10000000 100  -> loader.py load --rows 10000000 --tenants 100
                           [--prefix-rows 1000000 --prefix-tenants 10 when the
                           Phase 00 1M baseline is present] --allow-full-scale
                           (still refused unless AGRREGATEX_LOADER_ALLOW_FULL_SCALE=1)

Re-running the same command resumes an interrupted load.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loader  # noqa: E402


def main(argv):
    if len(argv) != 2 or (int(argv[0]), int(argv[1])) not in ((1_000_000, 10), (10_000_000, 100)):
        raise SystemExit('usage: load.py 1000000 10 | load.py 10000000 100  (see generator/loader.py --help)')
    rows, tenants = int(argv[0]), int(argv[1])
    args = ['load', '--rows', str(rows), '--tenants', str(tenants)]
    if rows > loader.FULL_SCALE_ROWS:
        try:
            L = loader.Loader(loader.resolve_dsn(None))
        except loader.Refused as e:
            print(f'REFUSED: {e}', file=sys.stderr); return loader.EXIT_REFUSED
        try:
            bulk = L.val('SELECT count(*) FROM public.orders WHERE id<0')
            run = L.get_run() if L.val("SELECT to_regclass('loader.runs') IS NOT NULL") else None
        finally:
            L.conn.close()
        if bulk == rows:
            print(f'already loaded: {bulk} bulk rows'); return 0
        unfinished = run if run and run['state'] not in ('active', 'aborted') else None
        prefix = unfinished['spec']['prefix_rows'] if unfinished else bulk
        if prefix:
            args += ['--prefix-rows', str(prefix), '--prefix-tenants', '10']
        args.append('--allow-full-scale')
    return loader.main(args)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
