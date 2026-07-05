"""
Scorer for the evaluation pipeline.

Given a list of (GroundTruth, Prediction) pairs, computes precision,
recall, and F1 using class-only matching: a prediction is a true positive
for class C if the prediction list contains C and the ground truth list
contains C for the same contract.

Metrics produced
----------------
- Per-class precision, recall, F1
- Overall micro-average  (aggregate TP/FP/FN across all classes)
- Overall macro-average  (mean of per-class scores)
- Total and mean runtime

Usage
-----
    from shared.core.scorer import score
    report = score(pairs)          # pairs: list[tuple[GroundTruth, Prediction]]
    print(report)
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Allow running directly: python3 shared/core/scorer.py
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import (
    GroundTruth,
    Prediction,
    VULNERABILITY_CLASSES,
)


@dataclass
class ClassMetrics:
    """Precision / recall / F1 for one vulnerability class."""
    vuln_class: str
    tp: int = 0   # ground truth has class C  AND  prediction has class C
    fp: int = 0   # ground truth lacks class C AND  prediction has class C
    fn: int = 0   # ground truth has class C  AND  prediction lacks class C

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def __str__(self) -> str:
        return (
            f"{self.vuln_class:<30} "
            f"P={self.precision:.3f}  R={self.recall:.3f}  F1={self.f1:.3f}  "
            f"(TP={self.tp} FP={self.fp} FN={self.fn})"
        )


@dataclass
class OverallMetrics:
    """Micro and macro averages across all classes."""
    # Micro: aggregate raw counts first, then compute rates
    micro_tp: int = 0
    micro_fp: int = 0
    micro_fn: int = 0
    # Macro: mean of per-class scores (only classes that appear in ground truth)
    macro_precision: float = 0.0
    macro_recall: float = 0.0
    macro_f1: float = 0.0

    @property
    def micro_precision(self) -> float:
        denom = self.micro_tp + self.micro_fp
        return self.micro_tp / denom if denom > 0 else 0.0

    @property
    def micro_recall(self) -> float:
        denom = self.micro_tp + self.micro_fn
        return self.micro_tp / denom if denom > 0 else 0.0

    @property
    def micro_f1(self) -> float:
        p, r = self.micro_precision, self.micro_recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


@dataclass
class ScorerReport:
    """Full scoring report for one tool run over a dataset."""
    tool_name: str
    num_contracts: int
    per_class: dict[str, ClassMetrics] = field(default_factory=dict)
    overall: OverallMetrics = field(default_factory=OverallMetrics)
    total_runtime_seconds: float = 0.0
    mean_runtime_seconds: float = 0.0
    # Per-contract detail: contract_id → {"gt_classes", "pred_classes", "tp", "fp", "fn"}
    contract_detail: list[dict] = field(default_factory=list)

    def summary_table(self) -> str:
        """Return a formatted multi-line summary string."""
        lines: list[str] = []
        lines.append(f"Tool: {self.tool_name}  |  contracts: {self.num_contracts}")
        lines.append(
            f"Runtime: total={self.total_runtime_seconds:.1f}s  "
            f"mean={self.mean_runtime_seconds:.2f}s"
        )
        lines.append("")
        lines.append(f"{'Class':<30} {'Precision':>9} {'Recall':>9} {'F1':>9}  Counts")
        lines.append("-" * 72)
        for cm in self.per_class.values():
            lines.append(
                f"{cm.vuln_class:<30} "
                f"{cm.precision:>9.3f} "
                f"{cm.recall:>9.3f} "
                f"{cm.f1:>9.3f}  "
                f"TP={cm.tp} FP={cm.fp} FN={cm.fn}"
            )
        lines.append("-" * 72)
        ov = self.overall
        lines.append(
            f"{'micro-avg':<30} "
            f"{ov.micro_precision:>9.3f} "
            f"{ov.micro_recall:>9.3f} "
            f"{ov.micro_f1:>9.3f}"
        )
        lines.append(
            f"{'macro-avg':<30} "
            f"{ov.macro_precision:>9.3f} "
            f"{ov.macro_recall:>9.3f} "
            f"{ov.macro_f1:>9.3f}"
        )
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.summary_table()


def score(
    pairs: list[tuple[GroundTruth, Prediction]],
    classes: Optional[list[str]] = None,
) -> ScorerReport:
    """Compute precision, recall, F1 for every class and overall.

    Parameters
    ----------
    pairs:
        List of (GroundTruth, Prediction) tuples for the same contracts.
        The contract_id fields must match within each pair.
    classes:
        Vulnerability classes to evaluate.  Defaults to
        ``VULNERABILITY_CLASSES``.

    Returns
    -------
    ScorerReport
    """
    if classes is None:
        classes = VULNERABILITY_CLASSES

    if not pairs:
        tool_name = "unknown"
        return ScorerReport(tool_name=tool_name, num_contracts=0)

    tool_name = pairs[0][1].tool_name

    # Initialise per-class counters
    class_metrics: dict[str, ClassMetrics] = {
        c: ClassMetrics(vuln_class=c) for c in classes
    }

    total_runtime = 0.0
    contract_detail: list[dict] = []

    for gt, pred in pairs:
        assert gt.contract_id == pred.contract_id, (
            f"contract_id mismatch: GT={gt.contract_id!r} vs "
            f"Pred={pred.contract_id!r}"
        )

        gt_classes = {v.vuln_class for v in gt.vulnerabilities}
        pred_classes = {v.vuln_class for v in pred.vulnerabilities}

        row_tp: dict[str, int] = {}
        row_fp: dict[str, int] = {}
        row_fn: dict[str, int] = {}

        for cls in classes:
            in_gt = cls in gt_classes
            in_pred = cls in pred_classes

            if in_gt and in_pred:
                class_metrics[cls].tp += 1
                row_tp[cls] = 1
            elif not in_gt and in_pred:
                class_metrics[cls].fp += 1
                row_fp[cls] = 1
            elif in_gt and not in_pred:
                class_metrics[cls].fn += 1
                row_fn[cls] = 1

        total_runtime += pred.runtime_seconds
        contract_detail.append({
            "contract_id": gt.contract_id,
            "gt_classes": sorted(gt_classes),
            "pred_classes": sorted(pred_classes),
            "tp": sorted(row_tp.keys()),
            "fp": sorted(row_fp.keys()),
            "fn": sorted(row_fn.keys()),
            "runtime_seconds": pred.runtime_seconds,
        })

    # Micro averages
    overall = OverallMetrics(
        micro_tp=sum(cm.tp for cm in class_metrics.values()),
        micro_fp=sum(cm.fp for cm in class_metrics.values()),
        micro_fn=sum(cm.fn for cm in class_metrics.values()),
    )

    # Macro averages — only over classes that appear in ground truth at least once
    active_classes = [
        cm for cm in class_metrics.values() if (cm.tp + cm.fn) > 0
    ]
    if active_classes:
        overall.macro_precision = sum(cm.precision for cm in active_classes) / len(active_classes)
        overall.macro_recall    = sum(cm.recall    for cm in active_classes) / len(active_classes)
        overall.macro_f1        = sum(cm.f1        for cm in active_classes) / len(active_classes)

    n = len(pairs)
    return ScorerReport(
        tool_name=tool_name,
        num_contracts=n,
        per_class=class_metrics,
        overall=overall,
        total_runtime_seconds=round(total_runtime, 3),
        mean_runtime_seconds=round(total_runtime / n, 3),
        contract_detail=contract_detail,
    )


# ---------------------------------------------------------------------------
# Standalone smoke-test — uses fabricated data, no real tool needed
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from shared.core.schema import Vulnerability

    # Build 6 synthetic (GroundTruth, Prediction) pairs:
    #   contract-1  GT=reentrancy          PRED=reentrancy           → TP reentrancy
    #   contract-2  GT=reentrancy          PRED=[]                   → FN reentrancy
    #   contract-3  GT=access_control      PRED=access_control       → TP access_control
    #   contract-4  GT=access_control      PRED=reentrancy           → FP reentrancy, FN access_control
    #   contract-5  GT=timestamp_dep.      PRED=timestamp_dep.       → TP timestamp_dep.
    #   contract-6  GT=[]  (out of scope)  PRED=reentrancy           → FP reentrancy

    def _gt(cid: str, cls: Optional[str]) -> GroundTruth:
        vulns = [Vulnerability(vuln_class=cls)] if cls else []
        return GroundTruth(contract_id=cid, contract_path=f"/fake/{cid}.sol", vulnerabilities=vulns)

    def _pred(cid: str, *classes: str) -> Prediction:
        vulns = [Vulnerability(vuln_class=c) for c in classes]
        return Prediction(contract_id=cid, tool_name="mock", vulnerabilities=vulns, runtime_seconds=1.0)

    pairs = [
        (_gt("c1", "reentrancy"),          _pred("c1", "reentrancy")),
        (_gt("c2", "reentrancy"),          _pred("c2")),
        (_gt("c3", "access_control"),      _pred("c3", "access_control")),
        (_gt("c4", "access_control"),      _pred("c4", "reentrancy")),
        (_gt("c5", "timestamp_dependency"), _pred("c5", "timestamp_dependency")),
        (_gt("c6", None),                  _pred("c6", "reentrancy")),
    ]

    report = score(pairs)
    print(report.summary_table())
    print()

    # Verify expected values
    assert report.per_class["reentrancy"].tp == 1
    assert report.per_class["reentrancy"].fp == 2   # c4 + c6
    assert report.per_class["reentrancy"].fn == 1   # c2
    assert report.per_class["access_control"].tp == 1
    assert report.per_class["access_control"].fp == 0
    assert report.per_class["access_control"].fn == 1  # c4
    assert report.per_class["timestamp_dependency"].tp == 1
    assert report.per_class["timestamp_dependency"].fp == 0
    assert report.per_class["timestamp_dependency"].fn == 0
    print("All assertions passed.")
