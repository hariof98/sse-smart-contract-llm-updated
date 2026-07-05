"""
Phase 4 — Hybrid (Slither → LLM filter) evaluation script.

Reads the cached Phase 0 Slither findings (does NOT re-run Slither), keeps the
in-scope ones, and asks an LLM to confirm/reject each. The confirmed subset is
the prediction. Repeated ``--runs`` times for variance; per-run JSON + CSV and a
variance summary are written under ``results/phase4_hybrid/<run-name>/``.

Usage
-----
    python3 -m phases.phase4_hybrid.run --model gpt4o-mini
    python3 -m phases.phase4_hybrid.run --model gpt4o
    python3 -m phases.phase4_hybrid.run --config primary_mini_hybrid
    python3 -m phases.phase4_hybrid.run --model gpt4o-mini --dry-run

Needs GITHUB_TOKEN in .env, and a cached Phase 0 Slither result
(results/phase0_traditional/slither_*.json). Models: see shared/config/models.py.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.datasets.smartbugs_loader import load_smartbugs
from shared.core.runner import run_evaluation
from shared.config.models import PHASE4_MODEL, COST_PER_1M
from phases.phase1_single_llm.reporting.llm_logger import attach_raw_metadata
from phases.phase4_hybrid.tools.llm_hybrid import make_tool, find_latest_slither_results
from phases.phase4_hybrid.reporting.hybrid_logger import log_phase4
from phases.phase4_hybrid import run_configs

_RESULTS_ROOT = _project_root / "results" / "phase4_hybrid"


def _f1(tp: int, fp: int, fn: int) -> float:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    return 2 * p * r / (p + r) if (p + r) else 0.0


def _contract_f1(detail: dict) -> float:
    return _f1(len(detail["tp"]), len(detail["fp"]), len(detail["fn"]))


def _std(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prices = COST_PER_1M.get(model)
    if not prices:
        return 0.0
    return (prompt_tokens / 1_000_000) * prices[0] + (completion_tokens / 1_000_000) * prices[1]


def _resolve_params(args) -> dict:
    """Resolve run parameters from --config and/or explicit CLI flags."""
    if args.config:
        cfg = run_configs.get_config(args.config)
        if cfg.get("kind") == "data_reuse":
            print(f"  [info] config '{args.config}' is a DATA-REUSE reference, not a run.")
            print(f"         {cfg.get('notes')}")
            print(f"         Nothing to execute. See hybrid_behaviour.py for the comparison.")
            sys.exit(0)
        return {
            "model": cfg["model"],
            "runs": cfg["runs"],
            "run_name": cfg["run_name"],
        }
    return {
        "model": args.model,
        "runs": args.runs,
        "run_name": args.run_name,   # may be None → filled from tool name later
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 4: hybrid Slither → LLM-filter evaluation.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--model", default=PHASE4_MODEL,
                        help=f"LLM used to review Slither findings (default: {PHASE4_MODEL}). "
                             "Configured in shared/config/models.py.")
    parser.add_argument("--dataset", default="smartbugs",
                        help="Dataset: 'smartbugs' (default), 'solidifi' (if a loader "
                             "exists), or a path to a dataset/ directory.")
    parser.add_argument("--runs", type=int, default=3,
                        help="Number of full runs for variance (default: 3).")
    parser.add_argument("--run-name", default=None,
                        help="Output subfolder under results/phase4_hybrid/ (default: tool name).")
    parser.add_argument("--slither-results", default=None,
                        help="Path to a cached Phase 0 slither_*.json "
                             "(default: newest in results/phase0_traditional/).")
    parser.add_argument("--config", default=None,
                        help="Load a prepared config from run_configs.py by name "
                             f"({', '.join(run_configs.RUN_CONFIGS)}). Overrides tuning flags.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process only the first 3 contracts (no files saved).")
    args = parser.parse_args()

    params = _resolve_params(args)

    # ── Locate the cached Slither results (never re-runs Slither) ─────────
    slither_path = (
        Path(args.slither_results) if args.slither_results
        else find_latest_slither_results()
    )
    if slither_path is None or not slither_path.exists():
        print("  [error] No cached Slither results found in results/phase0_traditional/.")
        print("          Run Phase 0 first:  python3 -m phases.phase0_traditional.run --tool slither")
        print("          Or pass one with:   --slither-results <path to slither_*.json>")
        sys.exit(1)

    # ── Build the tool ─────────────────────────────────────────────────────
    try:
        tool_fn = make_tool(model=params["model"], slither_results_path=slither_path)
    except ValueError as exc:
        print(f"  {exc}")
        sys.exit(1)

    tool_name = tool_fn.__name__
    run_name = params["run_name"] or tool_name
    run_dir = _RESULTS_ROOT / run_name

    ground_truths = _load_dataset(args.dataset)
    if args.dry_run:
        ground_truths = ground_truths[:3]

    print(f"\n  Model         : {params['model']}  (reviews Slither findings)")
    print(f"  Slither cache : {slither_path}")
    print(f"  Dataset       : {args.dataset}  ({len(ground_truths)} contracts)")
    print(f"  Runs          : {params['runs']}" + ("  [dry-run]" if args.dry_run else ""))
    print(f"  Run name      : {run_name}\n")

    # ── Execute runs ────────────────────────────────────────────────────────
    per_run_micro_f1: list[float] = []
    per_contract_f1: dict[str, list[float]] = {}
    grand_prompt = grand_completion = grand_tokens = 0
    skip_counts: list[int] = []

    for r in range(1, params["runs"] + 1):
        print(f"  ── Run {r}/{params['runs']} " + "─" * 40)
        predictions_raw: dict[str, str | None] = {}
        _fname_to_cid = {Path(gt.contract_path).name: gt.contract_id for gt in ground_truths}

        def _instrumented(contract_path: str):
            pred = tool_fn(contract_path)
            norm_id = _fname_to_cid.get(Path(contract_path).name, pred.contract_id)
            predictions_raw[norm_id] = pred.raw_output
            return pred

        report = run_evaluation(ground_truths, _instrumented, verbose=False, progress=True)
        report = attach_raw_metadata(report, predictions_raw)

        per_run_micro_f1.append(report.overall.micro_f1)
        for detail in report.contract_detail:
            per_contract_f1.setdefault(detail["contract_id"], []).append(_contract_f1(detail))

        skips = 0
        for meta in getattr(report, "_phase1_raw", {}).values():
            grand_prompt += meta.get("prompt_tokens", 0)
            grand_completion += meta.get("completion_tokens", 0)
            grand_tokens += meta.get("total_tokens", 0)
            if meta.get("skipped_llm"):
                skips += 1
        skip_counts.append(skips)

        if not args.dry_run:
            paths = log_phase4(report, results_dir=run_dir, run_index=r)
            print(f"      saved: {paths.json_path.name}")
        print()

    _print_summary(
        tool_name, params, per_run_micro_f1, per_contract_f1,
        grand_tokens, grand_prompt, grand_completion, skip_counts, len(ground_truths),
    )

    if not args.dry_run:
        variance_path = _write_variance(
            run_dir, tool_name, params, per_run_micro_f1, per_contract_f1,
            grand_tokens, grand_prompt, grand_completion, skip_counts, len(ground_truths),
        )
        print(f"  Variance summary: {variance_path}\n")
    else:
        print("  [dry-run] results not saved.\n")


def _load_dataset(dataset: str):
    if dataset == "smartbugs":
        return load_smartbugs()
    if dataset == "solidifi":
        print("  [error] No SolidiFI loader exists yet in shared/datasets/.")
        sys.exit(1)
    path = Path(dataset)
    if not path.exists():
        print(f"  [error] Dataset path not found: {path}")
        sys.exit(1)
    return load_smartbugs(path)


def _print_summary(
    tool_name, params, per_run_micro_f1, per_contract_f1,
    grand_tokens, grand_prompt, grand_completion, skip_counts, n_contracts,
) -> None:
    sep = "=" * 78
    runs = params["runs"]
    total_cost = _cost(params["model"], grand_prompt, grand_completion)
    mean_f1 = statistics.mean(per_run_micro_f1) if per_run_micro_f1 else 0.0
    std_f1 = _std(per_run_micro_f1)
    mean_skips = statistics.mean(skip_counts) if skip_counts else 0

    print(sep)
    print(f"  PHASE 4 RESULTS  —  {tool_name}")
    print(sep)
    print(f"  Model            : {params['model']}  (Slither-finding reviewer)")
    print(f"  Runs             : {runs}")

    print()
    print("  Micro-F1 across runs")
    print(f"  {'-'*54}")
    print(f"  Per run          : {', '.join(f'{v:.3f}' for v in per_run_micro_f1)}")
    print(f"  Mean ± std       : {mean_f1:.3f} ± {std_f1:.3f}")
    varied = sum(1 for vs in per_contract_f1.values() if _std(vs) > 1e-9)
    print(f"  Contracts varying across runs : {varied} / {len(per_contract_f1)}")

    print()
    print("  Efficiency (the point of the hybrid pattern)")
    print(f"  {'-'*54}")
    print(f"  {'Contracts where LLM was skipped':<40}: "
          f"{mean_skips:.0f} / {n_contracts}  ({mean_skips/n_contracts*100:.0f}% avg)")
    print(f"  {'Total LLM tokens (all runs)':<40}: {grand_tokens:>10,}")
    per_contract_tok = grand_tokens / (runs * n_contracts) if (runs * n_contracts) else 0
    print(f"  {'Tokens per contract (avg)':<40}: {per_contract_tok:>10,.0f}")
    if total_cost > 0:
        print(f"  {'Est. cost (OpenAI list price, all runs)':<40}: ${total_cost:>9.4f}")

    print(sep)
    print("  For the 3-way comparison (Slither / LLM / hybrid), skip rate, and")
    print("  false-positive reduction, run:")
    print(f"    python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour "
          f"--run-name {params['run_name'] or tool_name} --model {params['model']}")
    print(sep)


def _write_variance(
    run_dir, tool_name, params, per_run_micro_f1, per_contract_f1,
    grand_tokens, grand_prompt, grand_completion, skip_counts, n_contracts,
) -> Path:
    per_contract = {
        cid: {
            "f1_per_run": [round(v, 6) for v in vs],
            "mean_f1": round(statistics.mean(vs), 6) if vs else 0.0,
            "std_f1": round(_std(vs), 6),
        }
        for cid, vs in per_contract_f1.items()
    }
    payload = {
        "tool": tool_name,
        "model": params["model"],
        "runs": params["runs"],
        "num_contracts": n_contracts,
        "overall_micro_f1": {
            "per_run": [round(v, 6) for v in per_run_micro_f1],
            "mean": round(statistics.mean(per_run_micro_f1), 6) if per_run_micro_f1 else 0.0,
            "std": round(_std(per_run_micro_f1), 6),
        },
        "skips_per_run": skip_counts,
        "total_tokens": grand_tokens,
        "est_cost_usd": round(_cost(params["model"], grand_prompt, grand_completion), 6),
        "per_contract_f1": per_contract,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    variance_path = run_dir / "variance.json"
    variance_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return variance_path


if __name__ == "__main__":
    main()
