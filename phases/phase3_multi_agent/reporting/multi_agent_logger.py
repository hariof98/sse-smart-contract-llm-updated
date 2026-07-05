"""
Phase 3 logger — multi-agent (specialists + moderator) results.

Extends the base ``shared.core.logger`` (reusing ``_build_json_payload`` and
``_build_csv_rows``) with everything Phase 3 needs to log EVERYTHING:

  * Per-agent (three specialists + moderator) classes, token counts, runtimes,
    raw responses, and errors.
  * Per-contract role-token breakdown (cost dimension of RQ4).
  * The specialist union and the moderator's final list, so downstream
    analysis (``moderator_behaviour.py``) can reconstruct kept/dropped/added.

Writes the same two file types as every other phase (JSON + CSV), so downstream
tooling stays uniform. The per-run raw metadata is attached with Phase 1's
``attach_raw_metadata`` (reused, not duplicated) before calling ``log_phase3``.

Usage
-----
    from phases.phase1_single_llm.reporting.llm_logger import attach_raw_metadata
    from phases.phase3_multi_agent.reporting.multi_agent_logger import log_phase3
    report = attach_raw_metadata(report, predictions_raw)
    paths = log_phase3(report, results_dir=..., run_index=1)
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.logger import LogPaths, _build_json_payload, _build_csv_rows
from shared.core.schema import VULNERABILITY_CLASSES

_RESULTS_DIR = _project_root / "results" / "phase3_multi_agent"

_SPECIALIST_CLASSES = list(VULNERABILITY_CLASSES)


def log_phase3(
    report,
    results_dir: Path | None = None,
    *,
    timestamp: str | None = None,
    run_index: Optional[int] = None,
) -> LogPaths:
    """Write Phase 3 multi-agent results (JSON + CSV) with full per-agent detail.

    Expects ``report`` to already carry the ``_phase1_raw`` sidecar (attach it
    with ``reporting.llm_logger.attach_raw_metadata`` before calling this).

    Parameters
    ----------
    report:
        The scored ScorerReport for one run.
    results_dir:
        Output directory. Defaults to ``results/phase3_multi_agent/``.
    timestamp:
        UTC timestamp embedded in filenames. Auto-generated if None.
    run_index:
        1-based run number (for the multi-run variance loop). If given, the
        filename stem becomes ``<tool>_run<N>_<timestamp>``.
    """
    out_dir = Path(results_dir) if results_dir is not None else _RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    run_tag = f"_run{run_index}" if run_index is not None else ""
    stem = f"{report.tool_name}{run_tag}_{timestamp}"
    raw_meta: dict[str, dict] = getattr(report, "_phase1_raw", {})

    # ── JSON ──────────────────────────────────────────────────────────────
    payload = _build_json_payload(report)

    role_token_totals: dict[str, int] = {}
    skipped_count = 0

    for contract in payload["contracts"]:
        cid = contract["contract_id"]
        meta = raw_meta.get(cid, {})
        specialists = meta.get("specialists", {})
        moderator = meta.get("moderator", {})

        contract["model"]                 = meta.get("model", "")
        contract["use_moderator"]         = meta.get("use_moderator")
        contract["active_specialists"]    = meta.get("active_specialists", [])
        contract["skipped"]               = meta.get("skipped", False)
        contract["skip_reason"]           = meta.get("skip_reason")
        contract["estimated_source_tokens"] = meta.get("estimated_source_tokens", 0)

        # Per-specialist detail (classes / tokens / runtime / error / response).
        spec_out: dict[str, dict] = {}
        for cls in _SPECIALIST_CLASSES:
            sm = specialists.get(cls)
            if sm is None:
                continue
            spec_out[cls] = {
                "classes":         sm.get("classes", []),
                "total_tokens":    sm.get("total_tokens", 0),
                "runtime_seconds": sm.get("runtime_seconds", 0.0),
                "error":           sm.get("error"),
                "response":        sm.get("response", ""),
            }
        contract["specialists"] = spec_out
        contract["specialist_union_classes"] = meta.get("specialist_union_classes", [])

        contract["moderator"] = {
            "ran":               moderator.get("ran", False),
            "classes":           moderator.get("classes", []),
            "total_tokens":      moderator.get("total_tokens", 0),
            "runtime_seconds":   moderator.get("runtime_seconds", 0.0),
            "error":             moderator.get("error"),
            "fell_back_to_union": moderator.get("fell_back_to_union", False),
            "response":          moderator.get("response", ""),
        }

        contract["role_tokens"]  = meta.get("role_tokens", {})
        contract["total_tokens"] = meta.get("total_tokens", 0)
        contract["specialist_runtime_seconds"] = meta.get("specialist_runtime_seconds", 0.0)
        contract["moderator_runtime_seconds"]  = meta.get("moderator_runtime_seconds", 0.0)

        if meta.get("skipped"):
            skipped_count += 1
        for role, tok in (meta.get("role_tokens", {}) or {}).items():
            role_token_totals[role] = role_token_totals.get(role, 0) + int(tok or 0)

    # Aggregate token stats
    all_meta = list(raw_meta.values())
    total_tokens = sum(m.get("total_tokens", 0) for m in all_meta)
    n = report.num_contracts or 1

    payload["run_index"]          = run_index
    payload["total_tokens_used"]  = total_tokens
    payload["role_token_totals"]  = role_token_totals
    payload["mean_tokens_per_contract"] = round(total_tokens / n, 1)
    payload["skipped_contracts"]  = skipped_count

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ── CSV ───────────────────────────────────────────────────────────────
    fieldnames, rows = _build_csv_rows(report)
    extra_cols = [
        "model", "use_moderator", "skipped",
        "reentrancy_spec", "access_control_spec", "timestamp_dependency_spec",
        "specialist_union", "moderator_classes", "moderator_error",
        "reentrancy_spec_tokens", "access_control_spec_tokens",
        "timestamp_dependency_spec_tokens", "moderator_tokens", "total_tokens",
    ]
    fieldnames = fieldnames + extra_cols

    for row in rows:
        cid = row["contract_id"]
        meta = raw_meta.get(cid, {})
        specialists = meta.get("specialists", {})
        moderator = meta.get("moderator", {})
        role_tokens = meta.get("role_tokens", {}) or {}

        row["model"]         = meta.get("model", "")
        row["use_moderator"] = 1 if meta.get("use_moderator") else 0
        row["skipped"]       = 1 if meta.get("skipped") else 0
        for cls in _SPECIALIST_CLASSES:
            sm = specialists.get(cls, {})
            row[f"{cls}_spec"]        = "|".join(sm.get("classes", []))
            row[f"{cls}_spec_tokens"] = sm.get("total_tokens", 0)
        row["specialist_union"]  = "|".join(meta.get("specialist_union_classes", []))
        row["moderator_classes"] = "|".join(moderator.get("classes", []))
        row["moderator_error"]   = moderator.get("error") or ""
        row["moderator_tokens"]  = moderator.get("total_tokens", 0)
        row["total_tokens"]      = meta.get("total_tokens", 0)

    csv_path = out_dir / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return LogPaths(json_path=json_path, csv_path=csv_path)
