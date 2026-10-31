"""Read-only preflight for an explicitly approved disposable reference fault test."""
import json
import shutil
import subprocess
from pathlib import Path


def check(inspect, available_mb, swap_used_mb, free_bytes):
    if available_mb < 2048 or swap_used_mb > 1024 or free_bytes < 5*1024**3:
        raise ValueError('Resource gate: require 2GiB available, <=1GiB swap used, 5GiB disk')
    if not inspect or any(v.get('Labels', {}).get('io.aggregatex.disposable') != 'true' for v in inspect):
        raise ValueError('Every project database volume must carry io.aggregatex.disposable=true')
    if any(v.get('Labels', {}).get('com.docker.compose.project') != 'aggregatex-sharded' for v in inspect):
        raise ValueError('Volume project ownership mismatch')


if __name__ == '__main__':
    mem = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    names = subprocess.check_output(['docker','volume','ls','--filter','label=com.docker.compose.project=aggregatex-sharded','-q'],text=True,timeout=10).split()
    volumes = json.loads(subprocess.check_output(['docker','volume','inspect',*names],text=True,timeout=10)) if names else []
    if {v.get('Name') for v in volumes} != {'aggregatex-sharded_shard_a_data','aggregatex-sharded_shard_b_data'}:
        raise SystemExit('Unexpected disposable volume set')
    writer = json.loads(subprocess.check_output(['docker','inspect','aggregatex-sharded-writer-1'],text=True,timeout=10))[0]
    if writer['State']['Running']:
        raise SystemExit('Quiesce disposable writer first; exact oracle requires no concurrent writes')
    for service, volume in [('shard_a','aggregatex-sharded_shard_a_data'),('shard_b','aggregatex-sharded_shard_b_data')]:
        container = json.loads(subprocess.check_output(['docker','inspect',f'aggregatex-sharded-{service}-1'],text=True,timeout=10))[0]
        if container['Config']['Labels'].get('com.docker.compose.project') != 'aggregatex-sharded' or not any(m.get('Name') == volume and m.get('Destination') == '/var/lib/postgresql' for m in container['Mounts']):
            raise SystemExit('Unexpected database volume attachment')
    check(volumes,mem['MemAvailable']//1024,(mem['SwapTotal']-mem['SwapFree'])//1024,shutil.disk_usage('.').free)
