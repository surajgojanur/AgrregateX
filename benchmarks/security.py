import sys,json,uuid,datetime,platform
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from db import ROOT,run_python,query_json
from validation import source_snapshot
before=source_snapshot(query_json)
r=run_python(ROOT/'benchmarks/security_remote.py')
if r.returncode:raise RuntimeError(r.stderr)
d=json.loads(r.stdout);after=source_snapshot(query_json)
d.update({'schema_version':2,'runner_status':'COMPLETED','run':{'run_id':uuid.uuid4().hex,'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'platform':platform.platform(),'machine':platform.machine()},'source_snapshot':before,'source_snapshot_after':after,'baseline_cleanup_verified':before==after,'populated_tenants':before['populated_tenant_count']})
(ROOT/'benchmarks/results/security.json').write_text(json.dumps(d,indent=2));print('Security:',d['status'],len(d['tenants']),'tenant credentials','cleanup',d['baseline_cleanup_verified'])
