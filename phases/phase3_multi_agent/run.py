"""
Phase 3 — Multi-agent (specialists + moderator) evaluation script.

Runs the three-specialist + moderator pipeline over a dataset (SmartBugs
Curated by default — the same contracts and scorer as Phase 0/1/2), repeated
``--runs`` times to measure variance, and writes per-run JSON + CSV plus a
variance summary under ``results/phase3_multi_agent/<run-name>/``.

All four agents use the SAME model in a given run; specialisation is by system
prompt only. The moderator's final list is the prediction that gets scored.

Usage
-----
    python3 -m phases.phase3_multi_agent.run --model gpt-4o-mini
    python3 -m phases.phase3_multi_agent.run --model gpt-4o --token-cap 0        # uncapped
    python3 -m phases.phase3_multi_agent.run --model gpt-4o-mini --no-moderator  # union ablation
    python3 -m phases.phase3_multi_agent.run --model gpt-4o-mini --specialists reentrancy,access_control
    python3 -m phases.phase3_multi_agent.run --config ablation_no_moderator
    python3 -m phases.phase3_multi_agent.run --model gpt-4o-mini --dry-run        # first 3 contracts

Models (set provider in shared/config/models.py via USE_OPENAI):
    GitHub (free): gpt-4o-mini, gpt-4o   (needs GITHUB_TOKEN in .env)
    OpenAI (paid): gpt-4.1-nano, gpt-5.5, o3   (needs OPENAI_API_KEY in .env)
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
from shared.config.models import PHASE3_MODEL, PHASE3_TOKEN_CAP, COST_PER_1M
from phases.phase1_single_llm.reporting.llm_logger import attach_raw_metadata
from phases.phase3_multi_agent.tools.llm_multi_agent import make_tool, SPECIALISTS
from phases.phase3_multi_agent.reporting.multi_agent_logger import log_phase3
from phases.phase3_multi_agent import run_configs

_ALL_SPECIALISTS = [cls for cls, _ in SPECIALISTS]
_RESULTS_ROOT = _project_root / "results" / "phase3_multi_agent"


def _f1(tp: int, fp: int, fn: int) -> float:
    """Micro-F1 for a single contract's counts."""
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def _contract_f1(detail: dict) -> float:
    return _f1(len(detail["tp"]), len(detail["fp"]), len(detail["fn"]))


def _std(values: list[float]) -> float:
    """Sample standard deviation; 0.0 for fewer than two values."""
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
        params = {
            "model": cfg["model"],
            "token_cap": cfg["token_cap"],
            "use_moderator": cfg["use_moderator"],
            "specialist_classes": list(cfg["specialist_classes"]),
            "runs": cfg["runs"],
            "run_name": cfg["run_name"],
        }
        if params["token_cap"] is None:
            print(f"  [error] config '{args.config}' has token_cap = None (placeholder).")
            print("          Fill BUDGET_MATCHED_TOKEN_CAP in run_configs.py before running it.")
            sys.exit(1)
        return params

    # From explicit CLI flags (with config-file-independent defaults).
    if args.specialists:
        specialist_classes = [s.strip() for s in args.specialists.split(",") if s.strip()]
    else:
        specialist_classes = list(_ALL_SPECIALISTS)

    # --token-cap 0 means "uncapped".
    token_cap: Optional[int] = None if args.token_cap == 0 else args.token_cap

    return {
        "model": args.model,
        "token_cap": token_cap,
        "use_moderator": not args.no_moderator,
        "specialist_classes": specialist_classes,
        "runs": args.runs,
        "run_name": args.run_name,   # may be None → filled from tool name later
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 3: multi-agent (3 specialists + moderator) evaluation.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--model", default=PHASE3_MODEL,
                        help=f"Model used by ALL four agents (default: {PHASE3_MODEL}). "
                             "Configured in shared/config/models.py.")
    parser.add_argument("--dataset", default="smartbugs",
                        help="Dataset: 'smartbugs' (default), 'solidifi' (if a loader "
                             "exists), or a path to a dataset/ directory.")
    parser.add_argument("--runs", type=int, default=3,
                        help="Number of full runs for variance (default: 3).")
    parser.add_argument("--run-name", default=None,
                        help="Output subfolder name under results/phase3_multi_agent/ "
                             "(default: the tool name).")
    parser.add_argument("--token-cap", type=int, default=PHASE3_TOKEN_CAP,
                        help=f"Per-contract source token cap (default: {PHASE3_TOKEN_CAP}; "
                             "0 = uncapped).")
    parser.add_argument("--no-moderator", action="store_true",
                        help="Ablation: skip the moderator; final = deduped union of specialists.")
    parser.add_argument("--specialists", default=None,
                        help="Comma-separated specialist classes to run "
                             f"(default: all — {','.join(_ALL_SPECIALISTS)}).")
    parser.add_argument("--config", default=None,
                        help="Load a prepared config from run_configs.py by name "
                             f"({', '.join(run_configs.RUN_CONFIGS)}). Overrides the tuning flags.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process only the first 3 contracts (no files saved).")
    args = parser.parse_args()

    params = _resolve_params(args)

    # ── Validate ──────────────────────────────────────────────────────────
    unknown = [c for c in params["specialist_classes"] if c not in _ALL_SPECIALISTS]
    if unknown:
        print(f"  Unknown specialist class(es): {unknown}")
        print(f"  Choose from: {_ALL_SPECIALISTS}")
        sys.exit(1)

    # ── Build the tool ─────────────────────────────────────────────────────
    try:
        tool_fn = make_tool(
            model=params["model"],
            token_cap=params["token_cap"],
            use_moderator=params["use_moderator"],
            specialist_classes=params["specialist_classes"],
        )
    except ValueError as exc:
        print(f"  {exc}")
        sys.exit(1)

    tool_name = tool_fn.__name__
    run_name = params["run_name"] or tool_name
    run_dir = _RESULTS_ROOT / run_name

    # ── Load dataset ────────────────────────────────────────────────────────
    ground_truths = _load_dataset(args.dataset)
    if args.dry_run:
        ground_truths = ground_truths[:3]

    cap_str = "uncapped" if params["token_cap"] is None else str(params["token_cap"])
    print(f"\n  Model      : {params['model']}  (all four agents)")
    print(f"  Specialists: {', '.join(params['specialist_classes'])}")
    print(f"  Moderator  : {'on' if params['use_moderator'] else 'OFF (union ablation)'}")
    print(f"  Token cap  : {cap_str}")
    print(f"  Dataset    : {args.dataset}  ({len(ground_truths)} contracts)")
    print(f"  Runs       : {params['runs']}" + ("  [dry-run]" if args.dry_run else ""))
    print(f"  Run name   : {run_name}\n")

    # ── Execute runs ────────────────────────────────────────────────────────
    per_run_micro_f1: list[float] = []
    per_contract_f1: dict[str, list[float]] = {}
    role_token_totals: dict[str, int] = {}
    grand_prompt = grand_completion = 0

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

        # Aggregate role tokens + cost across runs.
        for meta in getattr(report, "_phase1_raw", {}).values():
            for role, tok in (meta.get("role_tokens", {}) or {}).items():
                role_token_totals[role] = role_token_totals.get(role, 0) + int(tok or 0)
            grand_prompt += meta.get("prompt_tokens", 0)
            grand_completion += meta.get("completion_tokens", 0)

        if not args.dry_run:
            paths = log_phase3(report, results_dir=run_dir, run_index=r)
            print(f"      saved: {paths.json_path.name}")
        print()

    _print_summary(
        tool_name=tool_name,
        params=params,
        per_run_micro_f1=per_run_micro_f1,
        per_contract_f1=per_contract_f1,
        role_token_totals=role_token_totals,
        grand_prompt=grand_prompt,
        grand_completion=grand_completion,
        n_contracts=len(ground_truths),
    )

    if not args.dry_run:
        variance_path = _write_variance(
            run_dir, tool_name, params, per_run_micro_f1, per_contract_f1,
            role_token_totals, grand_prompt, grand_completion, len(ground_truths),
        )
        print(f"  Variance summary: {variance_path}\n")
    else:
        print("  [dry-run] results not saved.\n")


def _load_dataset(dataset: str):
    """Resolve the --dataset argument to a list of GroundTruth."""
    if dataset == "smartbugs":
        return load_smartbugs()
    if dataset == "solidifi":
        print("  [error] No SolidiFI loader exists yet in shared/datasets/.")
        print("          Add one returning GroundTruth[] and re-run with --dataset solidifi.")
        sys.exit(1)
    # Otherwise treat it as a path to a SmartBugs-style dataset/ directory.
    path = Path(dataset)
    if not path.exists():
        print(f"  [error] Dataset path not found: {path}")
        sys.exit(1)
    return load_smartbugs(path)


def _print_summary(
    *,
    tool_name: str,
    params: dict,
    per_run_micro_f1: list[float],
    per_contract_f1: dict[str, list[float]],
    role_token_totals: dict[str, int],
    grand_prompt: int,
    grand_completion: int,
    n_contracts: int,
) -> None:
    sep = "=" * 78
    runs = params["runs"]
    total_tokens = sum(role_token_totals.values())
    total_cost = _cost(params["model"], grand_prompt, grand_completion)

    mean_f1 = statistics.mean(per_run_micro_f1) if per_run_micro_f1 else 0.0
    std_f1 = _std(per_run_micro_f1)

    print(sep)
    print(f"  PHASE 3 RESULTS  —  {tool_name}")
    print(sep)
    print(f"  Model            : {params['model']}  (all four agents)")
    print(f"  Specialists      : {', '.join(params['specialist_classes'])}")
    print(f"  Moderator        : {'on' if params['use_moderator'] else 'OFF (union ablation)'}")
    print(f"  Runs             : {runs}")

    print()
    print("  Micro-F1 across runs")
    print(f"  {'-'*54}")
    print(f"  Per run          : {', '.join(f'{v:.3f}' for v in per_run_micro_f1)}")
    print(f"  Mean ± std       : {mean_f1:.3f} ± {std_f1:.3f}")

    # Per-contract variance: how many contracts varied across runs.
    varied = sum(1 for vs in per_contract_f1.values() if _std(vs) > 1e-9)
    print(f"  Contracts varying across runs : {varied} / {len(per_contract_f1)}")

    print()
    print("  Tokens by agent role (summed across all runs)")
    print(f"  {'-'*54}")
    for role in list(role_token_totals.keys()):
        tok = role_token_totals[role]
        per_contract = tok / (runs * n_contracts) if (runs * n_contracts) else 0
        print(f"  {role:<32}: {tok:>10,}   ({per_contract:,.0f}/contract)")
    print(f"  {'TOTAL':<32}: {total_tokens:>10,}")
    if total_cost > 0:
        print(f"  {'Est. cost (OpenAI list price)':<32}: ${total_cost:>9.4f}")

    print(sep)
    print("  For moderator override rate and per-specialist recall, run:")
    print(f"    python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour "
          f"--run-name {params['run_name'] or tool_name}")
    print(sep)


def _write_variance(
    run_dir: Path,
    tool_name: str,
    params: dict,
    per_run_micro_f1: list[float],
    per_contract_f1: dict[str, list[float]],
    role_token_totals: dict[str, int],
    grand_prompt: int,
    grand_completion: int,
    n_contracts: int,
) -> Path:
    """Write variance.json capturing mean/std F1 across runs (overall + per contract)."""
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
        "use_moderator": params["use_moderator"],
        "specialists": params["specialist_classes"],
        "runs": params["runs"],
        "num_contracts": n_contracts,
        "overall_micro_f1": {
            "per_run": [round(v, 6) for v in per_run_micro_f1],
            "mean": round(statistics.mean(per_run_micro_f1), 6) if per_run_micro_f1 else 0.0,
            "std": round(_std(per_run_micro_f1), 6),
        },
        "role_token_totals": role_token_totals,
        "total_tokens": sum(role_token_totals.values()),
        "est_cost_usd": round(_cost(params["model"], grand_prompt, grand_completion), 6),
        "per_contract_f1": per_contract,
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    variance_path = run_dir / "variance.json"
    variance_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return variance_path


if __name__ == "__main__":
    main()
