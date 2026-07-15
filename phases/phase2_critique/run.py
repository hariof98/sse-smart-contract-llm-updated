"""
Phase 2 — Two-agent critique evaluation script.

Runs a cross-model detector -> critic pipeline over SmartBugs Curated (the
same 54 contracts and the same scorer as Phase 0/1), then reports per-class
precision/recall/F1 PLUS the two things Phase 2 exists to measure:

  1. Cost-adjusted performance (tokens per true positive, F1 per 1k tokens,
     F1 per dollar) — does the extra critic call justify itself?
  2. Critic behaviour breakdown (false positives removed, true positives
     wrongly removed, missed bugs recovered, agreement rate).

The detector and critic are different models (cross-model critique). The
critic's revised list is the final prediction that gets scored.

Usage
-----
    python3 -m phases.phase2_critique.run                                       # provider defaults
    python3 -m phases.phase2_critique.run --detector gpt-4o-mini --critic gpt-4o  # GitHub: cheap -> strong
    python3 -m phases.phase2_critique.run --detector gpt-4.1-nano --critic o3   # OpenAI: cheap -> strong
    python3 -m phases.phase2_critique.run --dry-run                             # 3 contracts

Models (set provider in shared/config/models.py via USE_OPENAI):
    GitHub (free): gpt-4o-mini, gpt-4o
    OpenAI (paid): gpt-4.1-nano, gpt-5.5, o3
"""

import argparse
import json
import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.datasets.smartbugs_loader import load_smartbugs
from shared.core.runner import run_evaluation
from shared.config.models import (
    PHASE2_DETECTOR, PHASE2_CRITIC, PHASE2_STRATEGY, COST_PER_1M as _COST_PER_1M,
)
from phases.phase1_single_llm.reporting.llm_logger import attach_raw_metadata
from phases.phase2_critique.reporting.critique_logger import log_phase2
from phases.phase1_single_llm.tools.llm_single_agent import SUPPORTED_MODELS
from phases.phase2_critique.tools.llm_critique import make_tool


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prices = _COST_PER_1M.get(model)
    if not prices:
        return 0.0
    return (prompt_tokens / 1_000_000) * prices[0] + (completion_tokens / 1_000_000) * prices[1]


def _fmt_cost(value: float) -> str:
    if value <= 0:
        return "$0.0000"
    if value < 0.0001:
        return "< $0.0001"
    return f"~${value:.4f}"


def _fmt_classes(classes: list[str]) -> str:
    return ", ".join(classes) if classes else "—"


def _print_contract_verbose(idx: int, total: int, contract_id: str, pred) -> None:
    """Print the original one-line progress format PLUS the critique detail.

    Line 1 is exactly what the runner would print (final findings = the critic's
    revised list). The indented lines below show the two-step pipeline the
    single line hides: what the detector reported, then what the critic changed.
    """
    try:
        meta = json.loads(pred.raw_output or "{}")
    except (json.JSONDecodeError, TypeError):
        meta = {}

    detector_classes = meta.get("detector_classes", [])
    critic_classes = meta.get("critic_classes", [])
    removed = meta.get("removed", [])
    added = meta.get("added", [])
    agreed = meta.get("agreed", False)
    detector_error = meta.get("detector_error")
    critic_error = meta.get("critic_error")

    # ── Line 1: the original runner format ────────────────────────────────
    final_classes = [v.vuln_class for v in pred.vulnerabilities]
    n_found = len(final_classes)
    classes_str = ", ".join(final_classes) or "—"
    print(f"[{idx:>3}/{total}] {contract_id} ... {pred.runtime_seconds:.1f}s  "
          f"findings={n_found} ({classes_str})")

    # ── Critique detail ───────────────────────────────────────────────────
    det_note = "  [detector call failed]" if detector_error else ""
    print(f"          detector -> {_fmt_classes(detector_classes)}{det_note}")

    if critic_error:
        print(f"          critic   -> (call failed — kept detector output)")
    elif agreed:
        print(f"          critic   -> {_fmt_classes(critic_classes)}   (no change)")
    else:
        edits = []
        if removed:
            edits.append(f"removed: {', '.join(removed)}")
        if added:
            edits.append(f"added: {', '.join(added)}")
        edit_note = f"   ({'; '.join(edits)})" if edits else ""
        print(f"          critic   -> {_fmt_classes(critic_classes)}{edit_note}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2: cross-model detector -> critic evaluation.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--detector", default=PHASE2_DETECTOR,
                        help=f"Detector model key (default: {PHASE2_DETECTOR}). "
                             "Configured in shared/config/models.py.")
    parser.add_argument("--critic", default=PHASE2_CRITIC,
                        help=f"Critic model key (default: {PHASE2_CRITIC}, a low-tier model "
                             "with a higher free-tier quota). Should differ from detector. "
                             "Configured in shared/config/models.py.")
    parser.add_argument("--strategy", default=PHASE2_STRATEGY,
                        help=f"Detector prompting strategy (default: {PHASE2_STRATEGY}).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process only the first 3 contracts (no files saved).")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show the detector's findings and the critic's revised "
                             "findings for each contract as it runs.")
    parser.add_argument("--dataset", default=None,
                        help="Override path to the SmartBugs dataset/ directory.")
    args = parser.parse_args()

    for role, model in (("detector", args.detector), ("critic", args.critic)):
        if model not in SUPPORTED_MODELS:
            print(f"  Unknown {role} model '{model}'.")
            print(f"  Choose from: {list(SUPPORTED_MODELS.keys())}")
            sys.exit(1)

    if args.detector == args.critic:
        print("  [warning] detector and critic are the same model — this is a "
              "self-critique, not the intended cross-model setup.\n")

    tool_fn = make_tool(detector=args.detector, critic=args.critic, strategy=args.strategy)

    dataset_root = Path(args.dataset) if args.dataset else None
    ground_truths = load_smartbugs(dataset_root)
    if args.dry_run:
        ground_truths = ground_truths[:3]

    print(f"\n  Detector : {args.detector}  ({SUPPORTED_MODELS[args.detector]})")
    print(f"  Critic   : {args.critic}  ({SUPPORTED_MODELS[args.critic]})")
    print(f"  Strategy : {args.strategy}")
    print(f"  Contracts: {len(ground_truths)}" + ("  [dry-run]\n" if args.dry_run else "\n"))

    # Capture each prediction's raw_output keyed by the normalised contract id.
    predictions_raw: dict[str, str | None] = {}
    _fname_to_cid = {Path(gt.contract_path).name: gt.contract_id for gt in ground_truths}

    total = len(ground_truths)
    counter = {"i": 0}

    def _instrumented(contract_path: str):
        pred = tool_fn(contract_path)
        norm_id = _fname_to_cid.get(Path(contract_path).name, pred.contract_id)
        predictions_raw[norm_id] = pred.raw_output
        if args.verbose:
            counter["i"] += 1
            _print_contract_verbose(counter["i"], total, norm_id, pred)
        return pred

    wall_start = time.monotonic()
    # In verbose mode we print our own detector/critic lines, so silence the
    # runner's one-line-per-contract progress to avoid interleaved output.
    report = run_evaluation(
        ground_truths, _instrumented, verbose=False, progress=not args.verbose
    )
    wall_elapsed = time.monotonic() - wall_start
    report = attach_raw_metadata(report, predictions_raw)

    _print_report(report, args, wall_elapsed, args.dry_run)

    if not args.dry_run:
        paths = log_phase2(report, results_dir=_project_root / "results" / "phase2_critique")
        print(f"  Results saved:")
        print(f"    {paths.json_path}")
        print(f"    {paths.csv_path}\n")


def _print_report(report, args, wall: float, dry_run: bool) -> None:
    raw_meta = list(getattr(report, "_phase1_raw", {}).values())
    detail_by_id = {d["contract_id"]: d for d in report.contract_detail}

    det_prompt = sum(m.get("detector_prompt_tokens", 0) for m in raw_meta)
    det_comp   = sum(m.get("detector_completion_tokens", 0) for m in raw_meta)
    crit_prompt = sum(m.get("critic_prompt_tokens", 0) for m in raw_meta)
    crit_comp   = sum(m.get("critic_completion_tokens", 0) for m in raw_meta)
    det_tokens = sum(m.get("detector_total_tokens", 0) for m in raw_meta)
    crit_tokens = sum(m.get("critic_total_tokens", 0) for m in raw_meta)
    total_tokens = sum(m.get("total_tokens", 0) for m in raw_meta)

    det_cost = _cost(args.detector, det_prompt, det_comp)
    crit_cost = _cost(args.critic, crit_prompt, crit_comp)
    total_cost = det_cost + crit_cost

    # Behaviour counts
    agg = {"agreed": 0, "fp_removed": 0, "tp_removed": 0, "tp_added": 0, "fp_added": 0}
    errors = 0
    raw_by_id = getattr(report, "_phase1_raw", {})
    for cid, meta in raw_by_id.items():
        gt = set(detail_by_id.get(cid, {}).get("gt_classes", []))
        removed = set(meta.get("removed", []))
        added = set(meta.get("added", []))
        if meta.get("agreed"):
            agg["agreed"] += 1
        agg["fp_removed"] += len(removed - gt)
        agg["tp_removed"] += len(removed & gt)
        agg["tp_added"]   += len(added & gt)
        agg["fp_added"]   += len(added - gt)
        if meta.get("detector_error") or meta.get("critic_error"):
            errors += 1

    pc = report.per_class
    ov = report.overall
    n = report.num_contracts or 1
    sep = "=" * 78

    print()
    print(sep)
    print(f"  PHASE 2 RESULTS  —  {report.tool_name}")
    print(sep)
    print(f"  Detector / Critic : {args.detector}  ->  {args.critic}")
    print(f"  Strategy          : {args.strategy}")
    print(f"  Contracts         : {report.num_contracts}")
    print(f"  Runtime           : {wall:.1f}s total  |  {report.mean_runtime_seconds:.1f}s per contract")
    if errors:
        print(f"  Pipeline errors   : {errors} / {report.num_contracts}  (detector or critic call failed)")

    print()
    print("  Token Usage & Cost")
    print(f"  {'-'*54}")
    print(f"  {'Detector tokens':<28}: {det_tokens:>10,}   {_fmt_cost(det_cost):>12}")
    print(f"  {'Critic tokens':<28}: {crit_tokens:>10,}   {_fmt_cost(crit_cost):>12}")
    print(f"  {'Total tokens':<28}: {total_tokens:>10,}   {_fmt_cost(total_cost):>12}")

    print()
    print("  Findings by Vulnerability Class")
    w = 24
    print(f"  {'Class':<{w}} {'TP':>4} {'FP':>4} {'FN':>4}  {'Precision':>9} {'Recall':>9} {'F1':>9}")
    print(f"  {'-'*(w+1)}{'-'*15}{'-'*30}")
    for cls, cm in pc.items():
        print(f"  {cls:<{w}} {cm.tp:>4} {cm.fp:>4} {cm.fn:>4}  "
              f"{cm.precision:>9.3f} {cm.recall:>9.3f} {cm.f1:>9.3f}")
    print(f"  {'-'*(w+1)}{'-'*15}{'-'*30}")
    print(f"  {'micro-average':<{w}} {ov.micro_tp:>4} {ov.micro_fp:>4} {ov.micro_fn:>4}  "
          f"{ov.micro_precision:>9.3f} {ov.micro_recall:>9.3f} {ov.micro_f1:>9.3f}")
    print(f"  {'macro-average':<{w}} {'':>4} {'':>4} {'':>4}  "
          f"{ov.macro_precision:>9.3f} {ov.macro_recall:>9.3f} {ov.macro_f1:>9.3f}")

    print()
    print("  Critic Behaviour (vs detector, classified against ground truth)")
    print(f"  {'-'*54}")
    print(f"  {'Agreed (no change)':<34}: {agg['agreed']:>4} / {n}  ({agg['agreed']/n*100:.0f}%)")
    print(f"  {'False positives removed (good)':<34}: {agg['fp_removed']:>4}")
    print(f"  {'True positives removed (bad)':<34}: {agg['tp_removed']:>4}")
    print(f"  {'True positives added (good)':<34}: {agg['tp_added']:>4}")
    print(f"  {'False positives added (bad)':<34}: {agg['fp_added']:>4}")

    print()
    print("  Cost-Adjusted Performance")
    print(f"  {'-'*54}")
    tpt = (total_tokens / ov.micro_tp) if ov.micro_tp else None
    f1_per_1k = (ov.micro_f1 / (total_tokens / 1000)) if total_tokens else None
    f1_per_dollar = (ov.micro_f1 / total_cost) if total_cost > 0 else None
    print(f"  {'Micro-F1':<34}: {ov.micro_f1:>8.3f}")
    print(f"  {'Tokens per true positive':<34}: {tpt:>8.1f}" if tpt else
          f"  {'Tokens per true positive':<34}: {'n/a':>8}")
    print(f"  {'F1 per 1k tokens':<34}: {f1_per_1k:>8.4f}" if f1_per_1k else
          f"  {'F1 per 1k tokens':<34}: {'n/a':>8}")
    if f1_per_dollar:
        print(f"  {'F1 per dollar (list price)':<34}: {f1_per_dollar:>8.2f}")
    else:
        print(f"  {'F1 per dollar (list price)':<34}: {'n/a (free tier)':>8}")
    print(sep)

    if dry_run:
        print("\n  [dry-run] results not saved.\n")


if __name__ == "__main__":
    main()
