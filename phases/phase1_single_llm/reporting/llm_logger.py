"""
Phase 1 logger — extends the base pipeline logger.

Writes the standard JSON + CSV (from core.logger) and additionally
enriches both files with Phase 1 specific fields extracted from raw_output:

Extra JSON fields (per contract in "contracts" array):
    strategy, prompt_tokens, completion_tokens, total_tokens,
    prompt_messages, response

Extra CSV columns (one per contract row):
    strategy, prompt_tokens, completion_tokens, total_tokens, response

Usage
-----
    from phases.phase1_single_llm.reporting.llm_logger import log_phase1
    paths = log_phase1(report)
"""

import csv
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.logger import log, LogPaths, _build_json_payload, _build_csv_rows
from shared.core.scorer import ScorerReport
from shared.core.schema import VULNERABILITY_CLASSES

_RESULTS_DIR = _project_root / "results"


def _parse_raw(raw_output: str | None) -> dict:
    """Extract Phase 1 metadata from a Prediction's raw_output JSON string."""
    if not raw_output:
        return {}
    try:
        return json.loads(raw_output)
    except (json.JSONDecodeError, TypeError):
        return {}


def log_phase1(
    report: ScorerReport,
    results_dir: Path | None = None,
    *,
    timestamp: str | None = None,
) -> LogPaths:
    """Write Phase 1 results with full token + prompt detail.

    Produces the same two files as pipeline.logger.log() but with
    additional columns/fields for strategy, token counts, and model
    responses.

    Parameters
    ----------
    report:
        ScorerReport from core.runner.run_evaluation().
    results_dir:
        Output directory. Defaults to <project_root>/results/.
    timestamp:
        UTC timestamp string embedded in filenames. Auto-generated if None.

    Returns
    -------
    LogPaths
        Paths to the JSON and CSV files written.
    """
    from datetime import datetime, timezone

    out_dir = Path(results_dir) if results_dir is not None else _RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    stem = f"{report.tool_name}_{timestamp}"

    # ── Build enriched JSON ───────────────────────────────────────────────
    payload = _build_json_payload(report)

    # Enrich each contract entry with Phase 1 metadata
    raw_lookup: dict[str, dict] = {}
    for detail in report.contract_detail:
        cid = detail["contract_id"]
        # raw_output is not in contract_detail (it's on the Prediction object)
        # We stored it separately in _phase1_raw when running; fall back to {}
        raw_lookup[cid] = {}

    # Attach raw metadata if available via _phase1_raw sidecar on the report
    phase1_raw: dict[str, dict] = getattr(report, "_phase1_raw", {})
    for contract in payload["contracts"]:
        cid = contract["contract_id"]
        meta = phase1_raw.get(cid, {})
        contract["strategy"]          = meta.get("strategy", "")
        contract["prompt_tokens"]     = meta.get("prompt_tokens", 0)
        contract["completion_tokens"] = meta.get("completion_tokens", 0)
        contract["total_tokens"]      = meta.get("total_tokens", 0)
        contract["prompt_messages"]   = meta.get("prompt_messages", [])
        contract["response"]          = meta.get("response", "")

    # Enrich top-level with aggregate token stats
    all_meta = list(phase1_raw.values())
    payload["total_prompt_tokens"]     = sum(m.get("prompt_tokens", 0)     for m in all_meta)
    payload["total_completion_tokens"] = sum(m.get("completion_tokens", 0) for m in all_meta)
    payload["total_tokens_used"]       = sum(m.get("total_tokens", 0)      for m in all_meta)

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ── Build enriched CSV ────────────────────────────────────────────────
    fieldnames, rows = _build_csv_rows(report)

    # Append Phase 1 extra columns
    extra_cols = [
        "strategy",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "response",
    ]
    fieldnames = fieldnames + extra_cols

    for row in rows:
        cid = row["contract_id"]
        meta = phase1_raw.get(cid, {})
        row["strategy"]          = meta.get("strategy", "")
        row["prompt_tokens"]     = meta.get("prompt_tokens", 0)
        row["completion_tokens"] = meta.get("completion_tokens", 0)
        row["total_tokens"]      = meta.get("total_tokens", 0)
        # Truncate long responses to keep CSV readable
        response = meta.get("response", "")
        row["response"] = response[:500].replace("\n", " ") if response else ""

    csv_path = out_dir / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return LogPaths(json_path=json_path, csv_path=csv_path)


def attach_raw_metadata(
    report: ScorerReport,
    predictions_raw: dict[str, str | None],
) -> ScorerReport:
    """Attach a _phase1_raw sidecar to *report* by parsing each Prediction's raw_output.

    Parameters
    ----------
    report:
        The ScorerReport to enrich.
    predictions_raw:
        Mapping of contract_id → raw_output string (from each Prediction).

    Returns
    -------
    ScorerReport
        The same report object, with a ``_phase1_raw`` attribute added.
    """
    phase1_raw: dict[str, dict] = {}
    for cid, raw in predictions_raw.items():
        phase1_raw[cid] = _parse_raw(raw)
    report._phase1_raw = phase1_raw  # type: ignore[attr-defined]
    return report
