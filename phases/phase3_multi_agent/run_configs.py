"""
Prepared Phase 3 experiment configurations (NOT auto-executed).

These describe the four runs to perform for the write-up. They are data only;
run them explicitly via ``run.py`` (either with the matching flags, or with
``--config <name>`` which loads the config from here).

    python3 -m phases.phase3_multi_agent.run --config budget_matched_mini
    python3 -m phases.phase3_multi_agent.run_configs        # print this table

Each config maps directly to the ``run.py`` / ``make_tool`` parameters:
    model, token_cap, use_moderator, specialist_classes, runs, run_name.

NOTE (placeholder): ``budget_matched_mini`` must be budget-matched to Phase 2's
best-run TOTAL token budget. Fill ``BUDGET_MATCHED_TOKEN_CAP`` in below once you
have that number from the Phase 2 results (results/phase2_critique/*.json →
``total_tokens_used``). It is intentionally left as None until then.
"""

from typing import Optional

# ── Placeholder — FILL ME IN ───────────────────────────────────────────────
# Target per-contract token budget for the budget-matched mini run, chosen so
# Phase 3's total spend matches Phase 2's best run. Left None on purpose.
BUDGET_MATCHED_TOKEN_CAP: Optional[int] = None  # TODO: set from Phase 2 best-run budget

# A practically-uncapped guard for the "uncapped" run (skips nothing realistic).
_UNCAPPED = 1_000_000

ALL_SPECIALISTS = ["reentrancy", "access_control", "timestamp_dependency"]


RUN_CONFIGS: dict[str, dict] = {
    # 1. gpt4o-mini, budget-matched to Phase 2's best-run token budget.
    "budget_matched_mini": {
        "model": "gpt4o-mini",
        "token_cap": BUDGET_MATCHED_TOKEN_CAP,   # None until filled in
        "use_moderator": True,
        "specialist_classes": ALL_SPECIALISTS,
        "runs": 3,
        "run_name": "budget_matched_mini",
        "notes": "Cost baseline for RQ4. token_cap is a PLACEHOLDER — set "
                 "BUDGET_MATCHED_TOKEN_CAP from Phase 2's best total token budget.",
    },
    # 2. gpt4o, uncapped.
    "uncapped_gpt4o": {
        "model": "gpt4o",
        "token_cap": _UNCAPPED,
        "use_moderator": True,
        "specialist_classes": ALL_SPECIALISTS,
        "runs": 3,
        "run_name": "uncapped_gpt4o",
        "notes": "Upper-bound quality run, no token cap.",
    },
    # 3. Ablation: gpt4o-mini with NO moderator (union of specialists, dedup).
    "ablation_no_moderator": {
        "model": "gpt4o-mini",
        "token_cap": 20000,
        "use_moderator": False,
        "specialist_classes": ALL_SPECIALISTS,
        "runs": 3,
        "run_name": "ablation_no_moderator",
        "notes": "Isolates the moderator's contribution: final = deduped union "
                 "of the three specialists.",
    },
    # 4. Ablation: gpt4o-mini with 2 specialists only (drop timestamp — the
    #    smallest class in the dataset).
    "ablation_two_specialists": {
        "model": "gpt4o-mini",
        "token_cap": 20000,
        "use_moderator": True,
        "specialist_classes": ["reentrancy", "access_control"],
        "runs": 3,
        "run_name": "ablation_two_specialists",
        "notes": "Drops the timestamp specialist (smallest class) to test the "
                 "cost/benefit of that specialist.",
    },
}


def get_config(name: str) -> dict:
    """Return the config dict for *name*, or raise with the valid options."""
    if name not in RUN_CONFIGS:
        raise KeyError(
            f"Unknown run config {name!r}. Choose from: {list(RUN_CONFIGS)}"
        )
    return RUN_CONFIGS[name]


if __name__ == "__main__":
    print("Phase 3 prepared run configurations (not auto-executed):\n")
    for name, cfg in RUN_CONFIGS.items():
        cap = cfg["token_cap"]
        cap_str = "PLACEHOLDER (None)" if cap is None else str(cap)
        specs = ",".join(cfg["specialist_classes"])
        print(f"  [{name}]")
        print(f"      model            : {cfg['model']}")
        print(f"      token_cap        : {cap_str}")
        print(f"      use_moderator    : {cfg['use_moderator']}")
        print(f"      specialists      : {specs}")
        print(f"      runs             : {cfg['runs']}")
        print(f"      run_name         : {cfg['run_name']}")
        print(f"      notes            : {cfg['notes']}")
        print()
    print("Run one with:  python3 -m phases.phase3_multi_agent.run --config <name>")
