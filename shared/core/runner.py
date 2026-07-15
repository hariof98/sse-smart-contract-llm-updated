"""
Runner — orchestrates a full tool evaluation over a dataset.

Given a list of GroundTruth objects and a tool function, runs the tool on
every contract, pairs each Prediction with its GroundTruth, and passes
everything to the scorer.

The tool function must match this signature:
    def run(contract_path: str) -> Prediction

That is the only contract a tool must fulfil to plug into the pipeline.

Usage
-----
    from shared.core.runner import run_evaluation
    from phases.phase0_traditional.tools.slither_tool import run as slither_run
    from shared.datasets.smartbugs_loader import load_smartbugs

    report = run_evaluation(load_smartbugs(), slither_run, verbose=True)
    print(report)
"""

import sys
import traceback
from pathlib import Path
from typing import Callable

# Allow running directly: python3 shared/core/runner.py
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import GroundTruth, Prediction, Vulnerability
from shared.core.scorer import ScorerReport, score

# Type alias for a tool function
ToolFn = Callable[[str], Prediction]


def run_evaluation(
    ground_truths: list[GroundTruth],
    tool_fn: ToolFn,
    *,
    verbose: bool = True,
    progress: bool = True,
) -> ScorerReport:
    """Run *tool_fn* on every contract in *ground_truths* and score.

    Parameters
    ----------
    ground_truths:
        Loaded dataset — one GroundTruth per contract.
    tool_fn:
        A callable ``(contract_path: str) -> Prediction``.  Must never
        raise; failures should be captured in ``Prediction.raw_output``.
    verbose:
        If True, print a one-line status for each contract as it finishes.
    progress:
        If True, print a summary line showing overall progress (N/total).

    Returns
    -------
    ScorerReport
        Fully scored report ready for logging.
    """
    total = len(ground_truths)
    pairs: list[tuple[GroundTruth, Prediction]] = []

    for i, gt in enumerate(ground_truths, start=1):
        if progress:
            print(f"[{i:>3}/{total}] {gt.contract_id}", end=" ... ", flush=True)

        try:
            pred = tool_fn(gt.contract_path)
        except Exception:
            # Tool raised unexpectedly — wrap the traceback in a safe Prediction
            # so the pipeline can continue and the scorer gets a full pair.
            pred = Prediction(
                contract_id=gt.contract_id,
                tool_name="unknown",
                vulnerabilities=[],
                runtime_seconds=0.0,
                raw_output=traceback.format_exc(),
            )

        # Ensure contract_id on the prediction always matches ground truth
        # (some tools derive it from the filename; normalise here).
        pred.contract_id = gt.contract_id

        if progress:
            n_found = len(pred.vulnerabilities)
            classes = ", ".join(v.vuln_class for v in pred.vulnerabilities) or "—"
            print(f"{pred.runtime_seconds:.1f}s  findings={n_found} ({classes})")

        pairs.append((gt, pred))

    report = score(pairs)

    if verbose:
        print()
        print(report.summary_table())

    return report


# ---------------------------------------------------------------------------
# Standalone smoke-test — uses a mock tool, no real Slither needed
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from shared.datasets.smartbugs_loader import load_smartbugs

    # Mock tool: always predicts the class that matches the contract's folder.
    # This gives a perfect score and confirms the runner wiring is correct.
    def perfect_tool(contract_path: str) -> Prediction:
        path = Path(contract_path)
        folder = path.parent.name   # e.g. "reentrancy"
        CLASS_MAP = {
            "reentrancy":      "reentrancy",
            "access_control":  "access_control",
            "time_manipulation": "timestamp_dependency",
        }
        vuln_class = CLASS_MAP.get(folder)
        vulns = [Vulnerability(vuln_class=vuln_class)] if vuln_class else []
        return Prediction(
            contract_id=path.name,
            tool_name="perfect_mock",
            vulnerabilities=vulns,
            runtime_seconds=0.001,
        )

    print("=== Runner smoke-test (perfect mock tool) ===\n")
    ground_truths = load_smartbugs()
    report = run_evaluation(ground_truths, perfect_tool, verbose=True, progress=True)

    # A perfect tool must score 1.0 everywhere
    for cm in report.per_class.values():
        assert cm.precision == 1.0, f"{cm.vuln_class} precision={cm.precision}"
        assert cm.recall    == 1.0, f"{cm.vuln_class} recall={cm.recall}"
        assert cm.f1        == 1.0, f"{cm.vuln_class} f1={cm.f1}"
    assert report.overall.micro_f1 == 1.0
    print("\nAll assertions passed — runner wiring is correct.")
