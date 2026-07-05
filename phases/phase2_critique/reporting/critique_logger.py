"""
Phase 2 logger — critique pipeline results.

Extends the base core logger with everything Phase 2 needs:

  * Per-step token breakdown (detector vs critic).
  * Cost-adjusted metrics (tokens per true positive, F1 per 1k tokens) — the
    metric the lit review demanded and most papers omit.
  * Critic behaviour breakdown, classified against ground truth:
        fp_removed  critic dropped a detector finding that was NOT in GT  (good)
        tp_removed  critic dropped a detector finding that WAS in GT      (bad)
        tp_added    critic added a finding that WAS in GT                 (good)
        fp_added    critic added a finding that was NOT in GT             (bad)
        agreed      critic made no change

Writes the same two file types as every other phase (JSON + CSV in results/),
so downstream analysis stays uniform.

Usage
-----
    from phases.phase2_critique.reporting.critique_logger import log_phase2
    from phases.phase1_single_llm.reporting.llm_logger import attach_raw_metadata   # reused as-is
    report = attach_raw_metadata(report, predictions_raw)
    paths = log_phase2(report)
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.logger import LogPaths, _build_json_payload, _build_csv_rows

_RESULTS_DIR = _project_root / "results"


def _classify_behavior(gt_classes: list[str], meta: dict) -> dict:
    """Classify the critic's edits against ground truth for one contract."""
    gt = set(gt_classes)
    removed = set(meta.get("removed", []))
    added = set(meta.get("added", []))
    return {
        "fp_removed": sorted(removed - gt),   # good: dropped a false positive
        "tp_removed": sorted(removed & gt),   # bad:  dropped a true positive
        "tp_added":   sorted(added & gt),     # good: recovered a missed bug
        "fp_added":   sorted(added - gt),     # bad:  introduced a false positive
    }


def log_phase2(
    report,
    results_dir: Path | None = None,
    *,
    timestamp: str | None = None,
) -> LogPaths:
    """Write Phase 2 critique results (JSON + CSV) with cost + behaviour detail.

    Expects ``report`` to already carry the ``_phase1_raw`` sidecar (attach it
    with ``reporting.llm_logger.attach_raw_metadata`` before calling this).
    """
    out_dir = Path(results_dir) if results_dir is not None else _RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    stem = f"{report.tool_name}_{timestamp}"
    raw_meta: dict[str, dict] = getattr(report, "_phase1_raw", {})

    # ── JSON ──────────────────────────────────────────────────────────────
    payload = _build_json_payload(report)

    # Per-contract enrichment + aggregate behaviour counts
    agg = {"agreed": 0, "fp_removed": 0, "tp_removed": 0, "tp_added": 0, "fp_added": 0}
    detail_by_id = {d["contract_id"]: d for d in report.contract_detail}

    for contract in payload["contracts"]:
        cid = contract["contract_id"]
        meta = raw_meta.get(cid, {})
        gt_classes = detail_by_id.get(cid, {}).get("gt_classes", [])
        behavior = _classify_behavior(gt_classes, meta)

        contract["strategy"]          = meta.get("strategy", "")
        contract["detector_model"]    = meta.get("detector_model", "")
        contract["critic_model"]      = meta.get("critic_model", "")
        contract["detector_classes"]  = meta.get("detector_classes", [])
        contract["critic_classes"]    = meta.get("critic_classes", [])
        contract["removed"]           = meta.get("removed", [])
        contract["added"]             = meta.get("added", [])
        contract["agreed"]            = meta.get("agreed", False)
        contract["behavior"]          = behavior
        contract["detector_total_tokens"] = meta.get("detector_total_tokens", 0)
        contract["critic_total_tokens"]   = meta.get("critic_total_tokens", 0)
        contract["total_tokens"]      = meta.get("total_tokens", 0)
        contract["detector_response"] = meta.get("detector_response", "")
        contract["critic_response"]   = meta.get("critic_response", "")
        contract["detector_error"]    = meta.get("detector_error")
        contract["critic_error"]      = meta.get("critic_error")

        if meta.get("agreed"):
            agg["agreed"] += 1
        for k in ("fp_removed", "tp_removed", "tp_added", "fp_added"):
            agg[k] += len(behavior[k])

    # Aggregate tokens
    all_meta = list(raw_meta.values())
    detector_tokens = sum(m.get("detector_total_tokens", 0) for m in all_meta)
    critic_tokens   = sum(m.get("critic_total_tokens", 0)   for m in all_meta)
    total_tokens    = sum(m.get("total_tokens", 0)          for m in all_meta)

    n = report.num_contracts or 1
    micro_tp = report.overall.micro_tp
    micro_f1 = report.overall.micro_f1

    payload["detector_tokens"] = detector_tokens
    payload["critic_tokens"]   = critic_tokens
    payload["total_tokens_used"] = total_tokens
    payload["behavior_counts"] = agg
    payload["agreed_rate"] = round(agg["agreed"] / n, 4)
    payload["cost_adjusted"] = {
        # tokens spent per correct detection (lower = more cost-efficient)
        "tokens_per_true_positive": round(total_tokens / micro_tp, 1) if micro_tp else None,
        # micro-F1 normalised by token spend (higher = more cost-efficient)
        "f1_per_1k_tokens": round(micro_f1 / (total_tokens / 1000), 6) if total_tokens else None,
        "total_tokens": total_tokens,
        "micro_f1": round(micro_f1, 6),
    }

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ── CSV ───────────────────────────────────────────────────────────────
    fieldnames, rows = _build_csv_rows(report)
    extra_cols = [
        "strategy", "detector_model", "critic_model",
        "detector_classes", "critic_classes", "removed", "added", "agreed",
        "fp_removed", "tp_removed", "tp_added", "fp_added",
        "detector_total_tokens", "critic_total_tokens", "total_tokens",
        "critic_response",
    ]
    fieldnames = fieldnames + extra_cols

    for row in rows:
        cid = row["contract_id"]
        meta = raw_meta.get(cid, {})
        gt_classes = detail_by_id.get(cid, {}).get("gt_classes", [])
        behavior = _classify_behavior(gt_classes, meta)

        row["strategy"]         = meta.get("strategy", "")
        row["detector_model"]   = meta.get("detector_model", "")
        row["critic_model"]     = meta.get("critic_model", "")
        row["detector_classes"] = "|".join(meta.get("detector_classes", []))
        row["critic_classes"]   = "|".join(meta.get("critic_classes", []))
        row["removed"]          = "|".join(meta.get("removed", []))
        row["added"]            = "|".join(meta.get("added", []))
        row["agreed"]           = 1 if meta.get("agreed") else 0
        row["fp_removed"]       = "|".join(behavior["fp_removed"])
        row["tp_removed"]       = "|".join(behavior["tp_removed"])
        row["tp_added"]         = "|".join(behavior["tp_added"])
        row["fp_added"]         = "|".join(behavior["fp_added"])
        row["detector_total_tokens"] = meta.get("detector_total_tokens", 0)
        row["critic_total_tokens"]   = meta.get("critic_total_tokens", 0)
        row["total_tokens"]     = meta.get("total_tokens", 0)
        resp = meta.get("critic_response", "")
        row["critic_response"]  = resp[:500].replace("\n", " ") if resp else ""

    csv_path = out_dir / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return LogPaths(json_path=json_path, csv_path=csv_path)
