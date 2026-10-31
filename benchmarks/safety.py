#!/usr/bin/env python3
"""Run G-3 in the API image while sampling Podman and PostgreSQL telemetry."""
import datetime
import json
import os
import platform
import selectors
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from db import ROOT, query_json
sys.path.insert(0, str(Path(__file__).parent))
from validation import source_snapshot

POSTGRES_CONTAINER = "agrregatex-postgres-1"
API_CONTAINER = "agrregatex-api-1"
MARKER_CENTS = 987654321
MARKER_FROM = "2099-01-01T00:00:00Z"
MARKER_TO = "2100-01-01T00:00:00Z"
TELEMETRY_SQL = """
SELECT json_build_object(
 'captured_at_utc', clock_timestamp(),
 'database', (SELECT json_build_object('xact_commit',xact_commit,'blks_read',blks_read,'blks_hit',blks_hit,
   'tup_returned',tup_returned,'tup_fetched',tup_fetched,'tup_inserted',tup_inserted,'tup_updated',tup_updated,
   'tup_deleted',tup_deleted,'temp_files',temp_files,'temp_bytes',temp_bytes,'deadlocks',deadlocks,
   'blk_read_time_ms',blk_read_time,'blk_write_time_ms',blk_write_time)
   FROM pg_stat_database WHERE datname=current_database()),
 'wal', (SELECT json_build_object('wal_records',wal_records,'wal_fpi',wal_fpi,'wal_bytes',wal_bytes,
   'wal_buffers_full',wal_buffers_full) FROM pg_stat_wal),
 'locks_total',(SELECT count(*) FROM pg_locks),
 'lock_waiters',(SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock'),
 'wait_events',(SELECT coalesce(json_object_agg(coalesce(wait_event_type,'none'),n),'{}'::json)
   FROM (SELECT wait_event_type,count(*) n FROM pg_stat_activity
         WHERE datname=current_database() GROUP BY wait_event_type) q)
)::text;
"""


def env_values():
    return dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if "=" in line)


def db_telemetry():
    result = subprocess.run(["podman", "exec", POSTGRES_CONTAINER, "psql", "-X", "-qAt",
                             "-v", "ON_ERROR_STOP=1", "-U", "agrregatex_owner", "-d", "agrregatex",
                             "-c", TELEMETRY_SQL], text=True, capture_output=True, timeout=8)
    if result.returncode:
        return {"error": result.stderr[-400:]}
    try:
        return json.loads(result.stdout.strip())
    except Exception as exc:
        return {"error": f"telemetry parse: {type(exc).__name__}", "raw": result.stdout[-300:]}


def container_telemetry():
    result = subprocess.run(["podman", "stats", "--no-stream", "--format",
                             "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.BlockIO}}",
                             POSTGRES_CONTAINER, API_CONTAINER], text=True, capture_output=True, timeout=8)
    if result.returncode:
        return {"error": result.stderr[-400:]}
    rows = []
    for line in result.stdout.splitlines():
        fields = line.split("|", 3)
        if len(fields) == 4:
            rows.append({"name": fields[0], "cpu": fields[1], "memory": fields[2], "block_io": fields[3]})
    return {"containers": rows}


def main():
    RESULTS = ROOT / "benchmarks/results"
    scale = int(sys.argv[1])
    before = source_snapshot(query_json)
    start = datetime.datetime.now(datetime.timezone.utc)
    env = env_values()
    marker_query = ("SELECT count(*) FROM orders WHERE ordered_at >= '" + MARKER_FROM + "'::timestamptz "
                    "AND ordered_at < '" + MARKER_TO + "'::timestamptz AND customer_id=100 "
                    "AND unit_price_cents=" + str(MARKER_CENTS))
    marker_before = int(subprocess.check_output(["podman", "exec", POSTGRES_CONTAINER, "psql", "-X", "-qAt",
                                                  "-U", "agrregatex_owner", "-d", "agrregatex", "-c", marker_query], text=True).strip())
    if marker_before:
        raise SystemExit(f"Safety fixture marker already exists ({marker_before} rows); refusing to touch it")
    year_query = ("SELECT count(*) FROM orders WHERE ordered_at >= '" + MARKER_FROM + "'::timestamptz "
                  "AND ordered_at < '" + MARKER_TO + "'::timestamptz")
    year_before = int(subprocess.check_output(["podman", "exec", POSTGRES_CONTAINER, "psql", "-X", "-qAt",
                                               "-U", "agrregatex_owner", "-d", "agrregatex", "-c", year_query], text=True).strip())
    if year_before:
        raise SystemExit(f"Reserved safety test date range contains {year_before} source rows; refusing to run")

    remote = ROOT / "benchmarks/safety_remote.py"
    admin_url = "postgresql://agrregatex_owner:" + env["DB_PASSWORD"] + "@postgres/agrregatex"
    prelude = "import os\nos.environ['ADMIN_DATABASE_URL']=" + repr(admin_url) + "\n"
    process = subprocess.Popen(["podman", "exec", "-i", API_CONTAINER, "python", "-u", "-"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, bufsize=1)
    process.stdin.write(prelude + remote.read_text())
    process.stdin.close()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    os.set_blocking(process.stdout.fileno(), False)
    state = {"phase": {"state": "startup"}}
    telemetry = []
    phase_events = []
    output_lines = []
    telemetry_errors = []
    pending = b""
    deadline = time.monotonic() + 780
    next_sample = time.monotonic()
    eof = False
    while (not eof or process.poll() is None) and time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_sample:
            sample = {"captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "phase": dict(state["phase"]), "podman": container_telemetry(), "postgres": db_telemetry()}
            if "error" in sample["podman"] or "error" in sample["postgres"]:
                telemetry_errors.append({"phase": sample["phase"], "podman": sample["podman"].get("error"), "postgres": sample["postgres"].get("error")})
            telemetry.append(sample)
            next_sample = time.monotonic() + 2
        ready = selector.select(timeout=.1)
        if ready:
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                eof = True
            else:
                pending += chunk
                while b"\n" in pending:
                    raw, pending = pending.split(b"\n", 1)
                    line = raw.decode(errors="replace") + "\n"
                    if line.startswith("@@PHASE "):
                        try:
                            event = json.loads(line[len("@@PHASE "):])
                            event["observed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                            state["phase"] = event
                            phase_events.append(event)
                        except Exception:
                            state["phase"] = {"state": "unparsed"}
                    else:
                        output_lines.append(line)
        if process.poll() is not None and not ready:
            # Drain remaining bytes, including the final unterminated line.
            try:
                chunk = os.read(process.stdout.fileno(), 65536)
            except BlockingIOError:
                chunk = b""
            if chunk:
                pending += chunk
            else:
                if pending:
                    output_lines.append(pending.decode(errors="replace"))
                    pending = b""
                eof = True
    timed_out = process.poll() is None
    if timed_out:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return_code = process.wait()
    selector.close()
    stderr = process.stderr.read()
    stdout = "".join(output_lines)
    (RESULTS / "safety-raw-stdout.log").write_text(stdout)
    (RESULTS / "safety-raw-stderr.log").write_text(stderr)
    remote_result = None
    for line in reversed(output_lines):
        try:
            candidate = json.loads(line)
            if isinstance(candidate, dict) and "metrics" in candidate and "arms" in candidate:
                remote_result = candidate
                break
        except Exception:
            pass

    cleanup_error = None
    if return_code != 0 or timed_out or remote_result is None:
        # This fingerprint was checked absent above; it scopes emergency cleanup
        # to test-owned rows if the remote harness exits before its finally block.
        cleanup_sql = ("BEGIN; DELETE FROM orders WHERE ordered_at >= '" + MARKER_FROM + "'::timestamptz AND ordered_at < '" + MARKER_TO + "'::timestamptz AND customer_id=100 AND unit_price_cents=" + str(MARKER_CENTS) + "; "
                       "DO $$ BEGIN IF EXISTS (SELECT 1 FROM orders WHERE ordered_at >= '" + MARKER_FROM + "'::timestamptz AND ordered_at < '" + MARKER_TO + "'::timestamptz) THEN RAISE EXCEPTION 'reserved safety date range is not empty'; END IF; END $$; "
                       "DELETE FROM daily_product WHERE bucket >= '" + MARKER_FROM + "'::timestamptz AND bucket < '" + MARKER_TO + "'::timestamptz AND n=0 AND units=0 AND cents=0; "
                       "DELETE FROM hourly_category WHERE bucket >= '" + MARKER_FROM + "'::timestamptz AND bucket < '" + MARKER_TO + "'::timestamptz AND n=0 AND units=0 AND cents=0; COMMIT")
        cleanup = subprocess.run(["podman", "exec", "-i", POSTGRES_CONTAINER, "psql", "-X", "-qAt",
                                  "-v", "ON_ERROR_STOP=1", "-U", "agrregatex_owner", "-d", "agrregatex",
                                  "-c", cleanup_sql], text=True, capture_output=True, timeout=120)
        if cleanup.returncode:
            cleanup_error = cleanup.stderr[-500:]
    after = source_snapshot(query_json)
    artifact = remote_result or {"status": "NOT TESTED", "error": "remote safety experiment did not return complete results"}
    artifact.update({"schema_version": 2, "runner_status": "FAILED" if return_code or timed_out or remote_result is None else "COMPLETED",
                     "run": {"run_id": uuid.uuid4().hex, "started_at_utc": start.isoformat(),
                             "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                             "host": platform.platform(), "machine": platform.machine()},
                     "dataset": {"dataset_id": "representative-seed42-v1" if scale == 1_000_000 else None,
                                 "scale": scale, "official_compatibility": "NOT_VERIFIED"},
                     "source_snapshot": before, "source_snapshot_after": after,
                     "source_cleanup_verified": before == after, "emergency_cleanup_error": cleanup_error,
                     "telemetry": telemetry, "phase_events": phase_events,
                     "telemetry_errors": telemetry_errors,
                     "telemetry_interval_seconds": 2, "telemetry_overhead": "Read-only Podman and pg_stat snapshots sampled by host during arms."})
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"safety-{scale}.json").write_text(json.dumps(artifact, indent=2))
    print(json.dumps({"runner_status": artifact["runner_status"], "status": artifact.get("status"),
                      "source_cleanup_verified": artifact["source_cleanup_verified"],
                      "metrics": artifact.get("metrics"), "telemetry_samples": len(telemetry),
                      "telemetry_errors": len(telemetry_errors)}, indent=2))
    if artifact["runner_status"] != "COMPLETED" or not artifact["source_cleanup_verified"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
