"""Offline policy and evidence classification for the Issue #31 G4 repro.

This module never connects to PostgreSQL. It deliberately requires observed
runtime artifacts before assigning a causal verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    aggregate_fast_path: bool | None
    merge_strategy: str | None
    merge_strategy_threshold: float | None


CONFIGS = {
    "primary_default": ExperimentConfig("primary_default", None, None, None),
    "comparison_fast_off_merge": ExperimentConfig(
        "comparison_fast_off_merge", False, "merge", None
    ),
    "comparison_fast_off_auto": ExperimentConfig(
        "comparison_fast_off_auto", False, "auto", 1.0
    ),
}

VALID_APPLY_PATHS = {
    "vector_agg",
    "delete_insert",
    "agg_fast_path",
    "merge",
    "merge_prepared",
    "pipeline",
    "explicit_dml",
}
VALID_PRODUCERS = {"p5_direct_sql", "standard_sql", "vector_agg", "unknown"}


def experiment_config(name: str) -> ExperimentConfig:
    """Return a safe, named run configuration; primary makes no tuning SETs."""
    try:
        return CONFIGS[name]
    except KeyError as exc:
        raise ValueError(f"unsupported G4 experiment configuration: {name}") from exc


def validate_sql_safety(sql: str, *, database: str, scheduler_enabled: bool) -> None:
    """Reject the protocol's known unsafe target conditions before running SQL."""
    if database != "ax_g4_repro":
        raise ValueError("G4 SQL is restricted to ax_g4_repro")
    if scheduler_enabled:
        raise ValueError("G4 SQL requires the isolated scheduler to be disabled")
    # A light offline tripwire, not a SQL parser/security boundary.
    normalized = " ".join(sql.lower().split())
    for forbidden in ("drop database", "truncate ", "alter role", "grant "):
        if forbidden in normalized:
            raise ValueError(f"forbidden SQL operation in G4 protocol: {forbidden.strip()}")


def classify_evidence(evidence: Mapping[str, Any]) -> str:
    """Classify completeness only; causal labels need complete observed stages.

    The runtime packet must include actual pre-compaction, post-compaction,
    post-visibility rows and executed apply-path evidence. Requested GUCs and
    SQL templates do not satisfy those requirements.
    """
    required = (
        "runtime_executed",
        "before_frontier",
        "after_frontier",
        "refresh_history",
        "raw_cdc",
        "stage_before_compaction",
        "stage_after_compaction",
        "stage_after_visibility",
        "producer_observed",
        "aggregate_delta_observed",
        "apply_observed",
        "oracle_results",
    )
    if any(key not in evidence or evidence[key] is None or evidence[key] == "" for key in required):
        return "INCONCLUSIVE"
    if evidence["runtime_executed"] is not True:
        return "INCONCLUSIVE"
    history = evidence["refresh_history"]
    if not isinstance(history, Mapping) or history.get("action") != "DIFFERENTIAL":
        return "INCONCLUSIVE"
    if history.get("status") != "COMPLETED" or history.get("was_full_fallback") is not False:
        return "INCONCLUSIVE"
    producer = evidence["producer_observed"]
    apply = evidence["apply_observed"]
    if producer not in VALID_PRODUCERS or apply not in VALID_APPLY_PATHS:
        return "INCONCLUSIVE"
    if producer == "unknown" or not evidence.get("frontiers_correlate"):
        return "INCONCLUSIVE"
    if not evidence.get("oracle_results"):
        return "INCONCLUSIVE"
    raw = evidence["raw_cdc"]
    before = evidence["stage_before_compaction"]
    compacted = evidence["stage_after_compaction"]
    visible = evidence["stage_after_visibility"]
    if not all(isinstance(rows, list) for rows in (raw, before, compacted, visible)):
        return "INCONCLUSIVE"
    if raw != before:
        return "INCONCLUSIVE"
    # A staging defect can only be localized when the negative event exists
    # before reduction and disappears at that exact boundary.
    negative = [r for r in before if r.get("action") == "D"]
    if negative and not any(r.get("action") == "D" for r in compacted):
        return "STAGING_DEFECT_CONFIRMED"
    return "INCONCLUSIVE"
