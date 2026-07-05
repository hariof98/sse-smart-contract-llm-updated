"""
Phase 0 end-to-end evaluation script.

Loads SmartBugs Curated, runs Slither over every in-scope contract,
scores predictions against ground truth, logs results to results/, and
prints a clean summary table.

Usage
-----
    python3 run_phase0.py                  # full run (54 contracts)
    python3 run_phase0.py --dry-run        # first 3 contracts only
    python3 run_phase0.py --tool mythril   # swap tool (once mythril_tool exists)
"""

import argparse
import sys
import time
from pathlib import Path

# Project root on sys.path (needed when run as a top-level script)
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.datasets.smartbugs_loader import load_smartbugs
from shared.core.logger import log
from shared.core.runner import run_evaluation


def _get_tool(name: str):
    """Return the tool's run() function by name."""
    if name == "slither":
        from phases.phase0_traditional.tools.slither_tool import run
        return run
    if name == "mythril":
        from phases.phase0_traditional.tools.mythril_tool import run  # type: ignore[import]
        return run
    raise ValueError(
        f"Unknown tool '{name}'. "
        "Add its run() function to tools/ and register it here."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 0: run a static-analysis tool over SmartBugs Curated."
    )
    parser.add_argument(
        "--tool",
        default=None,
        help="Tool to run: slither | mythril. If not specified, prompts at runtime.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process only the first 3 contracts (quick sanity check).",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Override path to the SmartBugs dataset/ directory.",
    )
    args = parser.parse_args()

    if args.tool is None:
        print("Available tools:")
        print("  1) slither (fast, static analysis)")
        print("  2) mythril (slow, symbolic execution)")
        choice = input("\nSelect a tool to run (1/2) [1]: ").strip()
        if choice in ("2", "mythril", "Mythril"):
            args.tool = "mythril"
        else:
            args.tool = "slither"
        print()

    # ── Load dataset ──────────────────────────────────────────────────────
    dataset_root = Path(args.dataset) if args.dataset else None
    ground_truths = load_smartbugs(dataset_root)

    if args.dry_run:
        ground_truths = ground_truths[:3]
        print(f"[dry-run] limiting to {len(ground_truths)} contracts\n")

    print(f"Dataset : SmartBugs Curated  ({len(ground_truths)} contracts)")
    print(f"Tool    : {args.tool}")
    print(f"Classes : reentrancy, access_control, timestamp_dependency")
    print()

    # ── Run evaluation ────────────────────────────────────────────────────
    tool_fn = _get_tool(args.tool)
    wall_start = time.monotonic()
    report = run_evaluation(ground_truths, tool_fn, verbose=False, progress=True)
    wall_elapsed = time.monotonic() - wall_start

    # ── Print summary ─────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print(report.summary_table())
    print("=" * 72)
    print(f"Wall time: {wall_elapsed:.1f}s")

    # ── Log results ───────────────────────────────────────────────────────
    if not args.dry_run:
        paths = log(report, results_dir=_project_root / "results" / "phase0_traditional")
        print()
        print("Results saved:")
        print(f"  {paths.json_path}")
        print(f"  {paths.csv_path}")
    else:
        print("\n[dry-run] results not saved to disk.")


if __name__ == "__main__":
    main()
