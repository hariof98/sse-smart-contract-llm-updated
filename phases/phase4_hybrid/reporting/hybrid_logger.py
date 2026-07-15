"""
Phase 4 logger — hybrid (Slither → LLM filter) results.

Extends the base ``shared.core.logger`` (reusing ``_build_json_payload`` and
``_build_csv_rows``) with everything Phase 4 needs to log EVERYTHING:

  * Slither's in-scope findings (the LLM's input) per contract.
  * The LLM's confirm/reject decisions per finding + raw response.
  * The skip flag (Slither found nothing in scope → no LLM call) + tokens.

Writes JSON + CSV like every other phase. Per-run raw metadata is attached with
Phase 1's ``attach_raw_metadata`` (reused) before calling ``log_phase4``.

Usage
-----
    from phases.phase1_single_llm.reporting.llm_logger import attach_raw_metadata
    from phases.phase4_hybrid.reporting.hybrid_logger import log_phase4
    report = attach_raw_metadata(report, predictions_raw)
    paths = log_phase4(report, results_dir=..., run_index=1)
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

_RESULTS_DIR = _project_root / "results" / "phase4_hybrid"


def log_phase4(
    report,
    results_dir: Path | None = None,
    *,
    timestamp: str | None = None,
    run_index: Optional[int] = None,
) -> LogPaths:
    """Write Phase 4 hybrid results (JSON + CSV) with full per-finding detail.

    Expects ``report`` to already carry the ``_phase1_raw`` sidecar (attach it
    with ``reporting.llm_logger.attach_raw_metadata`` before calling this).

    Parameters
    ----------
    report:
        The scored ScorerReport for one run.
    results_dir:
        Output directory. Defaults to ``results/phase4_hybrid/``.
    timestamp:
        UTC timestamp embedded in filenames. Auto-generated if None.
    run_index:
        1-based run number (multi-run variance loop). Stem becomes
        ``<tool>_run<N>_<timestamp>`` when given.
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

    total_tokens = 0
    skipped_count = 0
    slither_in_scope_total = 0
    confirmed_total = 0
    rejected_total = 0

    for contract in payload["contracts"]:
        cid = contract["contract_id"]
        meta = raw_meta.get(cid, {})

        in_scope = meta.get("slither_in_scope_findings", []) or []
        confirmed = meta.get("confirmed_classes", []) or []
        rejected = meta.get("rejected_classes", []) or []

        contract["model"]                     = meta.get("model", "")
        contract["slither_in_scope_findings"] = in_scope
        contract["skipped_llm"]               = meta.get("skipped_llm", False)
        contract["skip_reason"]               = meta.get("skip_reason")
        contract["reviewed"]                  = meta.get("reviewed", [])
        contract["confirmed_classes"]         = confirmed
        contract["rejected_classes"]          = rejected
        contract["llm_response"]              = meta.get("llm_response", "")
        contract["total_tokens"]              = meta.get("total_tokens", 0)
        contract["error"]                     = meta.get("error")

        total_tokens += meta.get("total_tokens", 0)
        if meta.get("skipped_llm"):
            skipped_count += 1
        slither_in_scope_total += len(in_scope)
        confirmed_total += len(confirmed)
        rejected_total += len(rejected)

    n = report.num_contracts or 1
    payload["run_index"]              = run_index
    payload["total_tokens_used"]      = total_tokens
    payload["mean_tokens_per_contract"] = round(total_tokens / n, 1)
    payload["skipped_llm_contracts"]  = skipped_count
    payload["skip_rate"]              = round(skipped_count / n, 4)
    payload["slither_in_scope_total"] = slither_in_scope_total
    payload["confirmed_total"]        = confirmed_total
    payload["rejected_total"]         = rejected_total

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── CSV ───────────────────────────────────────────────────────────────
    fieldnames, rows = _build_csv_rows(report)
    extra_cols = [
        "model", "skipped_llm", "slither_in_scope", "confirmed", "rejected",
        "total_tokens", "error",
    ]
    fieldnames = fieldnames + extra_cols

    for row in rows:
        cid = row["contract_id"]
        meta = raw_meta.get(cid, {})
        row["model"]            = meta.get("model", "")
        row["skipped_llm"]      = 1 if meta.get("skipped_llm") else 0
        row["slither_in_scope"] = "|".join(meta.get("slither_in_scope_findings", []) or [])
        row["confirmed"]        = "|".join(meta.get("confirmed_classes", []) or [])
        row["rejected"]         = "|".join(meta.get("rejected_classes", []) or [])
        row["total_tokens"]     = meta.get("total_tokens", 0)
        row["error"]            = meta.get("error") or ""

    csv_path = out_dir / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return LogPaths(json_path=json_path, csv_path=csv_path)
