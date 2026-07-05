"""
Phase 1 — Single-model LLM evaluation script.

Evaluates ONE model using the chain_of_thought prompting strategy
sequentially over all SmartBugs Curated contracts (54 contracts,
3 vulnerability classes).

Strategy is fixed to chain_of_thought — it achieved the best F1 score
across all models in preliminary trials and is well-suited to structured
code analysis tasks.

Produces:
  • Terminal summary table (per-class + overall metrics, token usage, cost)
  • JSON + CSV result files in results/

Usage
-----
    python3 run_phase1.py                  # gpt4o  (default)
    python3 run_phase1.py --model gpt4o-mini
    python3 run_phase1.py --model gpt41
    python3 run_phase1.py --dry-run        # 3 contracts only (quick smoke-test)

Available models: gpt4o-mini | gpt4o | gpt41
"""

import argparse
import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.datasets.smartbugs_loader import load_smartbugs
from shared.core.runner import run_evaluation
from shared.config.models import PHASE1_MODEL, PHASE1_STRATEGY, COST_PER_1M as _COST_PER_1M
from phases.phase1_single_llm.reporting.llm_logger import log_phase1, attach_raw_metadata
from phases.phase1_single_llm.tools.llm_single_agent import SUPPORTED_MODELS

# Default strategy — chain_of_thought outperformed zero_shot and few_shot
# across all models in preliminary trials. Configured in shared/config/models.py.
STRATEGY = PHASE1_STRATEGY

def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> str:
    """Return a human-readable cost estimate string."""
    prices = _COST_PER_1M.get(model)
    if not prices or (prompt_tokens + completion_tokens) == 0:
        return "n/a"
    input_cost  = (prompt_tokens    / 1_000_000) * prices[0]
    output_cost = (completion_tokens / 1_000_000) * prices[1]
    total = input_cost + output_cost
    if total < 0.0001:
        return "< $0.0001"
    return f"~${total:.4f}"

def _print_report(
    report,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    errors: int,
    wall: float,
    dry_run: bool,
) -> None:
    """Print a structured results summary matching the Phase 0 JSON format."""
    pc = report.per_class
    ov = report.overall
    cost = _estimate_cost(model, prompt_tokens, completion_tokens)
    sep = "=" * 78

    print()
    print(sep)
    print(f"  PHASE 1 RESULTS  —  {report.tool_name}")
    print(sep)

    # ── Run info ──────────────────────────────────────────────────────────
    print(f"  Model        : {model}  ({SUPPORTED_MODELS[model]})")
    print(f"  Strategy     : {STRATEGY}")
    print(f"  Contracts    : {report.num_contracts}")
    print(f"  Runtime      : {wall:.1f}s total  "
          f"|  {report.mean_runtime_seconds:.1f}s per contract")
    if errors:
        print(f"  API errors   : {errors} / {report.num_contracts}  "
              f"(check GITHUB_TOKEN and rate limits)")

    # ── Token usage ───────────────────────────────────────────────────────
    print()
    print(f"  Token Usage")
    print(f"  {'─'*44}")
    print(f"  {'Prompt tokens':<28}: {prompt_tokens:>10,}")
    print(f"  {'Completion tokens':<28}: {completion_tokens:>10,}")
    print(f"  {'Total tokens':<28}: {total_tokens:>10,}")
    print(f"  {'Est. cost (OpenAI list price)':<28}: {cost:>10}")

    # ── Per-class findings ────────────────────────────────────────────────
    print()
    print(f"  Findings by Vulnerability Class")
    w = 26
    print(f"  {'─'*w}{'─'*6}{'─'*6}{'─'*6}  {'─'*10}{'─'*10}{'─'*10}")
    print(f"  {'Class':<{w}} {'TP':>5} {'FP':>5} {'FN':>5}  "
          f"{'Precision':>9} {'Recall':>9} {'F1':>9}")
    print(f"  {'─'*w}{'─'*6}{'─'*6}{'─'*6}  {'─'*10}{'─'*10}{'─'*10}")

    for cls, cm in pc.items():
        total_pred = cm.tp + cm.fp
        total_gt   = cm.tp + cm.fn
        print(f"  {cls:<{w}} {cm.tp:>5} {cm.fp:>5} {cm.fn:>5}  "
              f"{cm.precision:>9.3f} {cm.recall:>9.3f} {cm.f1:>9.3f}"
              f"   [pred {total_pred}, GT {total_gt}]")

    # ── Overall (micro + macro) ───────────────────────────────────────────
    print(f"  {'─'*w}{'─'*6}{'─'*6}{'─'*6}  {'─'*10}{'─'*10}{'─'*10}")
    print(f"  {'micro-average':<{w}} {ov.micro_tp:>5} {ov.micro_fp:>5} {ov.micro_fn:>5}  "
          f"{ov.micro_precision:>9.3f} {ov.micro_recall:>9.3f} {ov.micro_f1:>9.3f}"
          f"   [pred {ov.micro_tp + ov.micro_fp}, GT {ov.micro_tp + ov.micro_fn}]")
    print(f"  {'macro-average':<{w}} {'':>5} {'':>5} {'':>5}  "
          f"{ov.macro_precision:>9.3f} {ov.macro_recall:>9.3f} {ov.macro_f1:>9.3f}")
    print(sep)

    if dry_run:
        print("\n  [dry-run] results not saved.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1: evaluate one LLM on SmartBugs Curated (sequential).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--model", default=PHASE1_MODEL,
        help=(
            "Model to evaluate. Options:\n"
            "  gpt4o-mini   — GPT-4o Mini   (fast, cheap)\n"
            "  gpt4o        — GPT-4o        (balanced)   [default]\n"
            "  gpt41        — GPT-4.1       (capable)\n"
            "  gpt41-nano   — GPT-4.1 Nano  (fastest, cheapest)\n"
            "  gpt5         — GPT-5         (most capable)\n"
            "  gpt5-mini    — GPT-5 Mini    (capable, faster)\n"
            "  deepseek-r1  — DeepSeek-R1   (reasoning model)\n"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Process only the first 3 contracts (quick smoke-test, no files saved).",
    )
    parser.add_argument(
        "--dataset", default=None,
        help="Override path to the SmartBugs dataset/ directory.",
    )
    args = parser.parse_args()

    if args.model not in SUPPORTED_MODELS:
        print(f"  Unknown model '{args.model}'.")
        print(f"  Choose from: {list(SUPPORTED_MODELS.keys())}")
        sys.exit(1)

    from phases.phase1_single_llm.tools.llm_single_agent import make_tool
    tool_fn = make_tool(strategy=STRATEGY, model=args.model)

    dataset_root  = Path(args.dataset) if args.dataset else None
    ground_truths = load_smartbugs(dataset_root)
    if args.dry_run:
        ground_truths = ground_truths[:3]

    print(f"\n  Model    : {args.model}  ({SUPPORTED_MODELS[args.model]})")
    print(f"  Strategy : {STRATEGY}")
    print(f"  Contracts: {len(ground_truths)}"
          + ("  [dry-run]\n" if args.dry_run else "\n"))

    # ── Instrument tool_fn to capture raw_output keyed by normalized ID ───
    predictions_raw: dict[str, str | None] = {}
    errors = 0

    # Tool returns contract_id = filename only ("Foo.sol").
    # Runner normalises to "folder/Foo.sol".  Build the map upfront.
    _fname_to_cid = {
        Path(gt.contract_path).name: gt.contract_id
        for gt in ground_truths
    }

    def _instrumented(contract_path: str):
        import json as _json
        nonlocal errors
        pred = tool_fn(contract_path)
        norm_id = _fname_to_cid.get(Path(contract_path).name, pred.contract_id)
        predictions_raw[norm_id] = pred.raw_output
        # Count API errors for user feedback
        try:
            if _json.loads(pred.raw_output or "{}").get("error"):
                errors += 1
        except Exception:
            pass
        return pred

    # ── Run ───────────────────────────────────────────────────────────────
    wall_start = time.monotonic()
    report = run_evaluation(
        ground_truths, _instrumented, verbose=False, progress=True
    )
    wall_elapsed = time.monotonic() - wall_start

    report = attach_raw_metadata(report, predictions_raw)

    # ── Aggregate token stats ─────────────────────────────────────────────
    all_meta          = list(getattr(report, "_phase1_raw", {}).values())
    total_tokens      = sum(m.get("total_tokens", 0)      for m in all_meta)
    prompt_tokens     = sum(m.get("prompt_tokens", 0)     for m in all_meta)
    completion_tokens = sum(m.get("completion_tokens", 0) for m in all_meta)

    # ── Print ─────────────────────────────────────────────────────────────
    _print_report(
        report,
        model=args.model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        errors=errors,
        wall=wall_elapsed,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        paths = log_phase1(report, results_dir=_project_root / "results" / "phase1_single_llm")
        print(f"  Results saved:")
        print(f"    {paths.json_path}")
        print(f"    {paths.csv_path}\n")


if __name__ == "__main__":
    main()
