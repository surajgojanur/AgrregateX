"""Read-only preflight for an explicitly approved disposable reference fault test."""
import json
import shutil
import subprocess
from pathlib import Path


def disposable_volume_free_bytes(volumes, disk_usage=None):
    """Measure the least free space on the backing filesystems of owned volumes."""
    if not isinstance(volumes, list) or not volumes:
        raise ValueError('Cannot verify Docker database volume mountpoints')
    disk_usage = disk_usage or shutil.disk_usage
    free_bytes = []
    for volume in volumes:
        mountpoint = volume.get('Mountpoint') if isinstance(volume, dict) else None
        if not isinstance(mountpoint, str) or not Path(mountpoint).is_absolute():
            raise ValueError('Docker database volume mountpoint is missing or invalid')
        try:
            available = disk_usage(mountpoint).free
        except OSError as exc:
            raise ValueError(f'Cannot measure database volume mountpoint: {mountpoint}') from exc
        if type(available) is not int or available < 0:
            raise ValueError(f'Invalid free-space reading for database volume mountpoint: {mountpoint}')
        free_bytes.append(available)
    return min(free_bytes)


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
    volume_free_bytes = disposable_volume_free_bytes(volumes)
    check(volumes,mem['MemAvailable']//1024,(mem['SwapTotal']-mem['SwapFree'])//1024,volume_free_bytes)
