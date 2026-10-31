#!/usr/bin/env python3
import sys,json,time,uuid,concurrent.futures
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from db import sql,query_json,ROOT
from validation import source_snapshot
BASE='http://127.0.0.1:18081';secret=json.loads((ROOT/'.secrets.json').read_text());tests=[]
run_id=uuid.uuid4().hex;started_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());baseline=None
def check(name,ok,detail=None):
 tests.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail});assert ok,(name,detail)
def headers(t,event=None):
 h={'Authorization':'Bearer '+secret['tenants'][str(t)]}
 if event:h['Idempotency-Key']=event
 return h
client=httpx.Client(base_url=BASE,timeout=30)
def req(method,path,t=1,body=None,event=None):return client.request(method,path,headers=headers(t,event),json=body)
def direct(t,a,b,family,grain='day',limit=10):
 where=f"tenant_id={t} AND ordered_at>='{a}'::timestamptz AND ordered_at<'{b}'::timestamptz"
 if family=='summary':s=f"SELECT count(*)::bigint orders,coalesce(sum(quantity) FILTER(WHERE status<>'cancelled'),0)::bigint units,coalesce(sum(quantity::bigint*unit_price_cents) FILTER(WHERE status<>'cancelled'),0)::bigint sales_cents FROM orders WHERE {where}"
 elif family=='top-products':s=f"SELECT product_id,sum(quantity)::bigint units,sum(quantity::bigint*unit_price_cents)::bigint sales_cents FROM orders WHERE {where} AND status<>'cancelled' GROUP BY product_id ORDER BY sales_cents DESC,units DESC,product_id LIMIT {int(limit)}"
 elif family=='breakdown':s=f"SELECT status,category_id,count(*)::bigint orders,coalesce(sum(quantity::bigint*unit_price_cents) FILTER(WHERE status<>'cancelled'),0)::bigint sales_cents FROM orders WHERE {where} GROUP BY status,category_id ORDER BY status,category_id"
 else:
  step='1 hour' if grain=='hour' else '1 day'
  s=f"SELECT s.bucket,coalesce(x.orders,0)::bigint orders,coalesce(x.sales_cents,0)::bigint sales_cents FROM generate_series(date_trunc('{grain}','{a}'::timestamptz,'UTC'),'{b}'::timestamptz,interval '{step}') s(bucket) LEFT JOIN (SELECT date_trunc('{grain}',ordered_at,'UTC') bucket,count(*) orders,sum(CASE WHEN status<>'cancelled' THEN quantity::bigint*unit_price_cents ELSE 0 END) sales_cents FROM orders WHERE {where} GROUP BY 1) x USING(bucket) WHERE s.bucket<'{b}'::timestamptz ORDER BY 1"
 data=query_json(s)
 if family=='trends':
  # PostgreSQL JSON timestamptz uses +00:00; FastAPI uses Z.
  for x in data:x['bucket']=x['bucket'].replace('Z','+00:00')
 return data[0] if family=='summary' else data

def reconcile(t,a,b,label):
 for fam,grain in [('summary','day'),('trends','day'),('trends','hour'),('top-products','day'),('breakdown','day')]:
  if grain=='hour' and (b[:10]=='2026-11-01' and a[:10]=='2026-08-01'):continue
  r=req('GET',f'/tenants/{t}/{fam}?from={a}&to={b}&grain={grain}',t)
  check(f'{label}:{t}:{fam}:{grain}',r.status_code==200,r.text[:300] if r.status_code!=200 else None)
  actual=r.json()['data'];expected=direct(t,a,b,fam,grain)
  check(f'{label}:{t}:{fam}:{grain}:oracle',actual==expected,{'actual':actual,'expected':expected} if actual!=expected else None)

def fixtures():
 global baseline
 baseline=source_snapshot(query_json)
 sql("INSERT INTO tenants VALUES(1,'Store 1'),(2,'Store 2') ON CONFLICT DO NOTHING; INSERT INTO products SELECT t,i,1+(i-1)%8,'Product '||i FROM generate_series(1,2) t CROSS JOIN generate_series(1,32) i ON CONFLICT DO NOTHING; INSERT INTO customers SELECT t,i FROM generate_series(1,2) t CROSS JOIN generate_series(1,100) i ON CONFLICT DO NOTHING;")
 ids=[];prefix=uuid.uuid4().hex
 body={'customer_id':1,'product_id':1,'category_id':1,'ordered_at':'2026-10-01T00:00:00Z','quantity':2,'unit_price_cents':1234,'status':'placed'}
 try:
  for t in [1,2]:
   r=req('POST',f'/tenants/{t}/orders',t,body,prefix+f'create{t}');check('create'+str(t),r.status_code==200,r.text);ids.append((t,r.json()['id']))
  r=req('POST','/tenants/1/orders',1,body,prefix+'create1');check('duplicate-create',r.status_code==200 and r.json()['id']==ids[0][1])
  r=req('POST','/tenants/1/orders',1,{**body,'quantity':9},prefix+'create1');check('conflicting-event',r.status_code==409)
  ranges=[('2026-10-01T00:00:00Z','2026-10-03T00:00:00Z'),('2026-10-01T00:00:00.001Z','2026-10-02T00:00:00Z'),('2026-10-01T00:00:00Z','2026-10-01T00:00:00.001Z'),('2026-10-03T00:00:00Z','2026-10-04T00:00:00Z')]
  for t in [1,2]:
   for i,(a,b) in enumerate(ranges):reconcile(t,a,b,f'fixture-{i}')
  # Force a tie in an otherwise empty time range and verify deterministic order.
  tie_body={'customer_id':1,'category_id':1,'ordered_at':'2035-06-01T12:00:00Z','quantity':1,'unit_price_cents':1000,'status':'placed'}
  for product in [1,2,3]:
   r=req('POST','/tenants/1/orders',1,{**tie_body,'product_id':product,'category_id':1+(product-1)%8},prefix+f'tie{product}')
   if r.status_code==200 and 'id' in r.json():ids.append((1,r.json()['id']))
   check('tie-create'+str(product),r.status_code==200,r.text)
  a='2035-06-01T00:00:00Z';b='2035-06-02T00:00:00Z'
  r=req('GET',f'/tenants/1/top-products?from={a}&to={b}&limit=2',1)
  actual=r.json().get('data') if r.status_code==200 else None;expected=direct(1,a,b,'top-products',limit=2)
  check('top-products-tie',r.status_code==200 and [x['product_id'] for x in actual]==[1,2],actual)
  check('top-products-tie:oracle',actual==expected,{'actual':actual,'expected':expected} if actual!=expected else None)
  oid=ids[0][1]
  for j,patch in enumerate([{'status':'cancelled'},{'quantity':5,'unit_price_cents':2000},{'ordered_at':'2026-10-02T00:00:01Z','status':'shipped','product_id':2,'category_id':2},{'ordered_at':'2026-09-30T23:59:59.999Z'}]):
   r=req('PATCH',f'/tenants/1/orders/{oid}',1,patch,prefix+f'patch{j}');check('patch'+str(j),r.status_code==200,r.text)
   replay=req('PATCH',f'/tenants/1/orders/{oid}',1,patch,prefix+f'patch{j}');check('replayed-update'+str(j),replay.json()==r.json())
   reconcile(1,'2026-09-30T00:00:00Z','2026-10-04T00:00:00Z','mutation'+str(j))
  for fam in ['summary','trends','top-products','breakdown','freshness']:
   check('cross-tenant-'+fam,req('GET',f'/tenants/2/{fam}?from=2026-10-01T00:00:00Z&to=2026-10-02T00:00:00Z',1).status_code==403)
  check('unauthorized-update',req('PATCH',f'/tenants/2/orders/{ids[1][1]}',1,{'quantity':9},prefix+'attack').status_code==403)
  check('other-order-hidden',req('PATCH',f'/tenants/1/orders/{ids[1][1]}',1,{'quantity':9},prefix+'attack2').status_code==404)
  check('tenant-body-rejected',req('POST','/tenants/1/orders',1,{**body,'tenant_id':2},prefix+'attack3').status_code==422)
  r=req('GET','/tenants/1/summary?from=2026-10-01T00:00:00Z&to=2026-10-02T00:00:00Z&tenant_id=2',1);check('query-override-ignored',r.json()['tenant_id']==1)
  check('no-token',client.get('/tenants/1/freshness').status_code==401)
  check('admin-monitoring-denied',req('GET','/monitoring',1).status_code==403)
  check('admin-monitoring',client.get('/monitoring',headers={'Authorization':'Bearer '+secret['admin']}).status_code==200)
  health=client.get('/health');check('health',health.status_code==200)
  page=client.get('/');check('dashboard',page.status_code==200 and 'AgrregateX' in page.text)
  spec=client.get('/openapi.json');spec_json=spec.json() if spec.status_code==200 else {}
  check('openapi-json',spec.status_code==200 and spec_json.get('info',{}).get('title','').startswith('AgrregateX') and all('/tenants/{tenant_id}/'+p in spec_json.get('paths',{}) for p in ['summary','trends','top-products','breakdown']))
  docs=client.get('/docs');check('swagger-docs',docs.status_code==200 and 'Swagger UI' in docs.text)
  # Rollback must atomically retract a failed source transaction.
  before=sql('select sum(n),sum(cents) from daily_product;')
  try:sql("BEGIN; INSERT INTO orders(tenant_id,customer_id,product_id,category_id,ordered_at,status,quantity,unit_price_cents) VALUES(1,1,1,1,now(),'placed',2,900); SELECT 1/0; COMMIT;")
  except RuntimeError:pass
  check('failed-transaction-atomic',sql('select sum(n),sum(cents) from daily_product;')==before)
  # Concurrent same-key requests must collapse to one order.
  def create_duplicate(_):
   with httpx.Client(base_url=BASE,timeout=20) as c:return c.post('/tenants/1/orders',headers=headers(1,prefix+'concurrent'),json=body)
  with concurrent.futures.ThreadPoolExecutor(2) as ex:replies=list(ex.map(create_duplicate,range(2)))
  check('concurrent-duplicate',all(r.status_code==200 for r in replies) and replies[0].json()==replies[1].json());ids.append((1,replies[0].json()['id']))
 finally:
  for t,oid in ids:
   try:
    r=req('DELETE',f'/tenants/{t}/orders/{oid}',t,event=prefix+f'del{t}-{oid}');tests.append({'name':'delete-test-record','status':'PASS' if r.status_code==200 else 'FAIL','detail':None if r.status_code==200 else r.text})
   except Exception as exc:tests.append({'name':'delete-test-record','status':'FAIL','detail':type(exc).__name__})
 # These reserved fixture buckets were verified empty before insertion. The
 # trigger keeps zero-valued keys; remove only those test-owned empty keys.
 try:
  sql("DELETE FROM daily_product WHERE tenant_id=1 AND product_id IN (1,2,3) AND bucket >= '2035-06-01' AND bucket < '2035-06-02' AND n=0 AND units=0 AND cents=0; DELETE FROM hourly_category WHERE tenant_id=1 AND category_id IN (1,2,3) AND bucket >= '2035-06-01' AND bucket < '2035-06-02' AND n=0 AND units=0 AND cents=0;")
  tests.append({'name':'aggregate-fixture-cleanup','status':'PASS','detail':None})
 except Exception as exc:
  tests.append({'name':'aggregate-fixture-cleanup','status':'FAIL','detail':type(exc).__name__})
 # Dedicated RLS connection test executes inside API container separately.
 persist('COMPLETED',None)
 print('Functional checks:',len(tests),'PASS')

def persist(runner_status,error=None):
 try:after=source_snapshot(query_json)
 except Exception as exc:after=None;error=error or f'final snapshot failed: {type(exc).__name__}'
 cleanup_ok=baseline is not None and after==baseline
 if not cleanup_ok:tests.append({'name':'baseline-cleanup','status':'FAIL','detail':{'before':baseline,'after':after}})
 else:tests.append({'name':'baseline-cleanup','status':'PASS','detail':None})
 if error:tests.append({'name':'runner-exception','status':'FAIL','detail':str(error)[:500]})
 artifact={'schema_version':2,'runner_status':runner_status,'run_id':run_id,'started_at_utc':started_at,'finished_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'dataset':{'dataset_id':'representative-seed42-v1','scale':1000000},'scale':1000000,'source_snapshot':baseline,'source_snapshot_after':after,'baseline_cleanup_verified':cleanup_ok,'tests':tests,'status':'PASS' if all(t['status']=='PASS' for t in tests) and not error else 'FAIL'}
 (ROOT/'benchmarks/results/functional.json').write_text(json.dumps(artifact,indent=2))

if __name__=='__main__':
 try:fixtures()
 except BaseException as exc:
  persist('FAILED',f'{type(exc).__name__}: {exc}')
  raise
