#!/usr/bin/env python3
"""Compare matched HTTP request cases; absence of 10M evidence is explicitly NOT TESTED."""
import json,statistics
from pathlib import Path
r=Path(__file__).parent/'results'
a_path=r/'benchmark-1000000.json';b_path=r/'benchmark-10000000.json'
out={'target':'G-5','requirement':'<2x latency growth at 10M relative to 1M','status':'NOT TESTED','reason':'A valid 10M dataset/benchmark result is not present.'}
if a_path.exists() and b_path.exists():
 a=json.loads(a_path.read_text());b=json.loads(b_path.read_text())
 valid=(a.get('scale')==1_000_000 and b.get('scale')==10_000_000 and
        a.get('source_snapshot',{}).get('orders')==1_000_000 and a.get('source_snapshot',{}).get('tenants')==10 and
        b.get('source_snapshot',{}).get('orders')==10_000_000 and b.get('source_snapshot',{}).get('tenants')==100)
 if not valid:
  out={'target':'G-5','status':'NOT TESTED','reason':'Scale artifacts do not prove exactly 1M/10 tenants and 10M/100 tenants.'}
 else:
  def cells(d):
   result={}
   for x in d['requests']:
    if x.get('http')!=200:continue
    role='hot' if x['tenant']==1 else 'second' if x['tenant']==2 else 'small' if x['tenant']==(10 if d['scale']==1000000 else 100) else 'middle'
    key=':'.join([role,x['family'],x['grain'],x['range'],x['mode']]);result.setdefault(key,[]).append(x['ms'])
   return result
  ca,cb=cells(a),cells(b);cases=[]
  for key in sorted(ca.keys() & cb.keys()):
   x,y=sorted(ca[key]),sorted(cb[key]);p=lambda q:q[min(len(q)-1,int(.95*len(q)))]
   ratios={'p50':statistics.median(y)/statistics.median(x),'p95':p(y)/p(x),'max':max(y)/max(x)}
   cases.append({'case':key,'latency_1m_p50_ms':statistics.median(x),'latency_10m_p50_ms':statistics.median(y),'n_1m':len(x),'n_10m':len(y),'ratio':ratios,'status':'PASS' if max(ratios.values())<2 else 'FAIL'})
  out={'target':'G-5','status':'PASS' if cases and all(x['status']=='PASS' for x in cases) else 'FAIL' if cases else 'NOT TESTED','conditions':'Matched tenant role, query, range, endpoint concurrency; successful requests only; p50/p95/max ratios.','worst_ratio':max((max(x['ratio'].values()) for x in cases),default=None),'cases':cases}
(r/'growth.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
