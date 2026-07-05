"""
Logger — persists a ScorerReport to the results/ directory.

Writes two files per run:
  results/<tool>_<timestamp>.json   full detail (all contracts + metrics)
  results/<tool>_<timestamp>.csv    one row per contract (summary metrics)

Both filenames share the same timestamp so they are easy to pair up.

Usage
-----
    from shared.core.logger import log
    paths = log(report)
    print(paths.json_path, paths.csv_path)
"""

import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Allow running directly: python3 shared/core/logger.py
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.scorer import ScorerReport

_RESULTS_DIR = _project_root / "results"


@dataclass
class LogPaths:
    """Paths to the files written by a single log() call."""
    json_path: Path
    csv_path: Path

    def __str__(self) -> str:
        return f"JSON → {self.json_path}\n CSV → {self.csv_path}"


def _build_json_payload(report: ScorerReport) -> dict:
    """Serialise a ScorerReport to a plain dict (JSON-safe)."""
    per_class = {}
    for cls, cm in report.per_class.items():
        per_class[cls] = {
            "tp": cm.tp,
            "fp": cm.fp,
            "fn": cm.fn,
            "precision": round(cm.precision, 6),
            "recall":    round(cm.recall,    6),
            "f1":        round(cm.f1,        6),
        }

    ov = report.overall
    overall = {
        "micro": {
            "tp":        ov.micro_tp,
            "fp":        ov.micro_fp,
            "fn":        ov.micro_fn,
            "precision": round(ov.micro_precision, 6),
            "recall":    round(ov.micro_recall,    6),
            "f1":        round(ov.micro_f1,        6),
        },
        "macro": {
            "precision": round(ov.macro_precision, 6),
            "recall":    round(ov.macro_recall,    6),
            "f1":        round(ov.macro_f1,        6),
        },
    }

    return {
        "tool":                   report.tool_name,
        "num_contracts":          report.num_contracts,
        "total_runtime_seconds":  report.total_runtime_seconds,
        "mean_runtime_seconds":   report.mean_runtime_seconds,
        "per_class":              per_class,
        "overall":                overall,
        "contracts":              report.contract_detail,
    }


def _build_csv_rows(report: ScorerReport) -> tuple[list[str], list[dict]]:
    """Return (fieldnames, rows) for the per-contract CSV."""
    from shared.core.scorer import VULNERABILITY_CLASSES  # avoid circular at module level

    # Dynamically import so this module stays self-contained
    try:
        from shared.core.schema import VULNERABILITY_CLASSES as VC
    except ImportError:
        VC = list(report.per_class.keys())

    fieldnames = [
        "contract_id",
        "gt_classes",
        "pred_classes",
        "tp_classes",
        "fp_classes",
        "fn_classes",
        "runtime_seconds",
    ]
    # Add one column per class: 1 if in GT, 1 if predicted
    for cls in VC:
        fieldnames.append(f"gt_{cls}")
        fieldnames.append(f"pred_{cls}")

    rows = []
    for detail in report.contract_detail:
        row: dict = {
            "contract_id":      detail["contract_id"],
            "gt_classes":       "|".join(detail["gt_classes"]),
            "pred_classes":     "|".join(detail["pred_classes"]),
            "tp_classes":       "|".join(detail["tp"]),
            "fp_classes":       "|".join(detail["fp"]),
            "fn_classes":       "|".join(detail["fn"]),
            "runtime_seconds":  detail["runtime_seconds"],
        }
        for cls in VC:
            row[f"gt_{cls}"]   = 1 if cls in detail["gt_classes"]   else 0
            row[f"pred_{cls}"] = 1 if cls in detail["pred_classes"] else 0
        rows.append(row)

    return fieldnames, rows


def log(
    report: ScorerReport,
    results_dir: Path | None = None,
    *,
    timestamp: str | None = None,
) -> LogPaths:
    """Write *report* to JSON and CSV files under *results_dir*.

    Parameters
    ----------
    report:
        The scored report returned by ``pipeline.scorer.score()``.
    results_dir:
        Directory to write into.  Created if it does not exist.
        Defaults to ``<project_root>/results/``.
    timestamp:
        ISO-style string to embed in filenames.  Auto-generated (UTC) if
        not supplied.  Useful for deterministic filenames in tests.

    Returns
    -------
    LogPaths
        Paths to the two files that were written.
    """
    out_dir = Path(results_dir) if results_dir is not None else _RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    stem = f"{report.tool_name}_{timestamp}"

    # ── JSON ──────────────────────────────────────────────────────────────
    json_path = out_dir / f"{stem}.json"
    payload = _build_json_payload(report)
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ── CSV ───────────────────────────────────────────────────────────────
    csv_path = out_dir / f"{stem}.csv"
    fieldnames, rows = _build_csv_rows(report)
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return LogPaths(json_path=json_path, csv_path=csv_path)


# ---------------------------------------------------------------------------
# Standalone smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile
    from shared.core.schema import GroundTruth, Prediction, Vulnerability
    from shared.core.scorer import score

    def _gt(cid: str, cls: str) -> GroundTruth:
        return GroundTruth(
            contract_id=cid,
            contract_path=f"/fake/{cid}.sol",
            vulnerabilities=[Vulnerability(vuln_class=cls)],
        )

    def _pred(cid: str, *classes: str) -> Prediction:
        return Prediction(
            contract_id=cid,
            tool_name="mock",
            vulnerabilities=[Vulnerability(vuln_class=c) for c in classes],
            runtime_seconds=1.5,
        )

    pairs = [
        (_gt("c1", "reentrancy"),          _pred("c1", "reentrancy")),
        (_gt("c2", "reentrancy"),          _pred("c2")),
        (_gt("c3", "access_control"),      _pred("c3", "access_control")),
        (_gt("c4", "timestamp_dependency"), _pred("c4", "timestamp_dependency")),
    ]
    report = score(pairs)

    with tempfile.TemporaryDirectory() as tmp:
        paths = log(report, results_dir=Path(tmp), timestamp="TEST")

        # Verify JSON
        data = json.loads(paths.json_path.read_text())
        assert data["tool"] == "mock"
        assert data["num_contracts"] == 4
        assert data["per_class"]["reentrancy"]["tp"] == 1
        assert data["per_class"]["reentrancy"]["fn"] == 1
        print(f"[PASS] JSON written to {paths.json_path.name}")
        print(f"       keys: {list(data.keys())}")

        # Verify CSV
        rows = list(csv.DictReader(paths.csv_path.open(encoding="utf-8")))
        assert len(rows) == 4
        assert rows[0]["contract_id"] == "c1"
        assert rows[0]["gt_reentrancy"] == "1"
        assert rows[0]["pred_reentrancy"] == "1"
        assert rows[1]["pred_reentrancy"] == "0"   # c2: no prediction
        print(f"[PASS] CSV written to {paths.csv_path.name}")
        print(f"       columns: {list(rows[0].keys())}")

    print("\nAll assertions passed.")
