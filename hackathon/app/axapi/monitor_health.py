"""Fail-closed consumption of the operator-only, versioned health facade."""
import re


HEALTH_SQL = "SELECT check_name, severity, detail FROM ax.monitor_health_check()"
REQUIRED_CHECKS = frozenset((
    "scheduler_running", "error_tables", "stale_tables", "needs_reinit",
    "consecutive_errors", "buffer_growth", "slot_lag", "attachment_owner_check",
    "dvm_fallbacks", "ring_overflow_trend", "immediate_ivm_triggers",
    "publication_bindings", "freshness_evidence", "freshness_breach",
    "freshness_infeasible", "freshness_override", "adaptive_workers",
    "memory_budget", "scheduler_load", "disk_forecast", "monitor_contract",
))
SEVERITIES = frozenset(("OK", "WARN", "WARNING", "ERROR", "UNKNOWN"))


def _unknown(detail):
    return {"check_name": "monitor_contract", "severity": "UNKNOWN", "detail": detail}


def read_health(connection):
    """Never fall back to a privileged pool or expose database exception text."""
    try:
        rows = connection.execute(HEALTH_SQL).fetchall()
    except Exception as error:
        sqlstate = getattr(error, "sqlstate", None)
        code = sqlstate if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate) else "unavailable"
        return [_unknown(f"Operator health diagnostics unavailable (SQLSTATE {code}); verification required.")]
    valid = [row for row in rows if isinstance(row, dict)
             and isinstance(row.get("check_name"), str)
             and isinstance(row.get("detail"), str)
             and row.get("severity") in SEVERITIES]
    names = [row["check_name"] for row in valid]
    incomplete = (len(valid) != len(rows) or len(names) != len(set(names))
                  or not REQUIRED_CHECKS.issubset(names))
    if incomplete and not any(row["severity"] == "UNKNOWN" for row in valid):
        valid.append(_unknown("Incomplete health evidence; required checks must not be silently skipped."))
    return valid
