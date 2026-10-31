"""Exact per-shard oracle coverage, host-side, no database writes."""
import json
import os
import subprocess

TABLES = {'st_day_product_status','st_day_category_status','st_hour_category_status'}


def clean(rows):
    return (isinstance(rows,list) and len(rows)==3 and all(isinstance(r,dict) for r in rows)
            and {r.get('stream_table','').removeprefix('ax.') for r in rows} == TABLES
            and all(type(r.get(k)) is int and r[k]==0 for r in rows for k in ('missing_in_st','extra_in_st')))


if __name__ == '__main__':
    env = os.environ.copy()
    env['PGPASSWORD'] = env.get('AX_DB_SUPERUSER_PASSWORD','')
    if not env['PGPASSWORD']:
        raise SystemExit('Require AX_DB_SUPERUSER_PASSWORD; never use an existing database')
    for port in ('25571','25572'):
        query = "SET statement_timeout='5s'; SELECT coalesce(json_agg(r),'[]') FROM ax.oracle_mismatches() r;"
        raw = subprocess.check_output(['psql','-XAtq','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-p',port,'-U','postgres','-d','aggregatex','-c',query],env=env,text=True,timeout=10)
        if not clean(json.loads(raw)):
            raise SystemExit('FAIL: incomplete or nonzero shard oracle')
    print('Exact three-table oracle coverage PASS on both shards')
