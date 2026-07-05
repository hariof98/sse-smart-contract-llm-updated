"""
Prepared Phase 4 experiment configurations (NOT auto-executed).

These describe the runs to perform for the write-up. They are data only; run
them explicitly via ``run.py`` (with the matching flags, or ``--config <name>``).

    python3 -m phases.phase4_hybrid.run --config primary_mini_hybrid
    python3 -m phases.phase4_hybrid.run_configs        # print this table

Each config maps to the ``run.py`` / ``make_tool`` parameters (model, runs,
run_name). One config is a DATA-REUSE reference (no new run) — it points the
analysis script at existing Phase 1 results for the "LLM alone" comparison.

NOTE (placeholder): ``primary_mini_hybrid`` should be budget-matched to the
Phase 1 gpt4o-mini single-agent token budget. Fill
``BUDGET_MATCH_TARGET_TOKENS`` below from that run
(results/phase1_single_llm/gpt4o-mini_*.json → ``total_tokens_used``). It is a
reporting/comparison target, not a hard cap (the hybrid naturally uses ≤1 call
per contract and skips empty-Slither contracts).
"""

from typing import Optional

# ── Placeholder — FILL ME IN ───────────────────────────────────────────────
# Phase 1 gpt4o-mini single-agent total token budget, used as the comparison
# target for the budget-matched hybrid run. Left None on purpose.
BUDGET_MATCH_TARGET_TOKENS: Optional[int] = None  # TODO: set from Phase 1 gpt4o-mini run


RUN_CONFIGS: dict[str, dict] = {
    # 1. Primary: gpt4o-mini + Slither hybrid, budget-matched to Phase 1
    #    gpt4o-mini single-agent (target is a reporting comparison, not a cap).
    "primary_mini_hybrid": {
        "kind": "run",
        "model": "gpt4o-mini",
        "runs": 3,
        "run_name": "primary_mini_hybrid",
        "budget_match_target_tokens": BUDGET_MATCH_TARGET_TOKENS,  # None until filled
        "notes": "Primary RQ2 run. Compare cost-adjusted F1 vs Phase 1 gpt4o-mini "
                 "single-agent. Fill BUDGET_MATCH_TARGET_TOKENS for the comparison.",
    },
    # 2. Comparison reference: gpt4o ALONE from Phase 1 — DATA REUSE, no new run.
    #    The analysis script pulls these numbers from existing Phase 1 results.
    "comparison_gpt4o_single": {
        "kind": "data_reuse",
        "model": "gpt4o",
        "source": "results/phase1_single_llm/gpt4o_chain_of_thought_*.json",
        "notes": "No new run. Reuse Phase 1 gpt4o single-agent results as the "
                 "'LLM alone (strong)' comparison point. Pass this model to "
                 "hybrid_behaviour.py via --compare-llm-model gpt4o if needed.",
    },
    # 3. Ablation: gpt4o + Slither hybrid, uncapped. Does the hybrid still help
    #    with a strong LLM, or is the value concentrated in cheap models?
    "ablation_gpt4o_hybrid": {
        "kind": "run",
        "model": "gpt4o",
        "runs": 3,
        "run_name": "ablation_gpt4o_hybrid",
        "budget_match_target_tokens": None,   # uncapped / not budget-matched
        "notes": "Strong-LLM hybrid. Tests whether the filter value is "
                 "concentrated in cheap models or persists with gpt4o.",
    },
}


def get_config(name: str) -> dict:
    """Return the config dict for *name*, or raise with the valid options."""
    if name not in RUN_CONFIGS:
        raise KeyError(f"Unknown run config {name!r}. Choose from: {list(RUN_CONFIGS)}")
    return RUN_CONFIGS[name]


if __name__ == "__main__":
    print("Phase 4 prepared run configurations (not auto-executed):\n")
    for name, cfg in RUN_CONFIGS.items():
        print(f"  [{name}]  ({cfg['kind']})")
        print(f"      model : {cfg['model']}")
        if cfg["kind"] == "run":
            tgt = cfg.get("budget_match_target_tokens")
            tgt_str = "PLACEHOLDER (None)" if tgt is None else str(tgt)
            print(f"      runs             : {cfg['runs']}")
            print(f"      run_name         : {cfg['run_name']}")
            print(f"      budget target    : {tgt_str}")
        else:
            print(f"      source           : {cfg.get('source')}")
        print(f"      notes            : {cfg['notes']}")
        print()
    print("Run one with:  python3 -m phases.phase4_hybrid.run --config <name>")
    print("(the 'data_reuse' config performs no run — it is a comparison pointer.)")
