# results/ — Run outputs

Outputs are grouped into one subfolder per phase; each run's entry point writes
into its own folder automatically:

```
results/
├── phase0_traditional/   Slither / Mythril runs
├── phase1_single_llm/    single-LLM runs
├── phase2_critique/      detector → critic runs (+ _comparison.* and the canvas)
├── phase3_multi_agent/   specialists + moderator runs, one subfolder per --run-name
└── phase4_hybrid/        LLM-filters-Slither runs, one subfolder per --run-name
```

Phases 3 and 4 differ slightly: each `--run-name` gets its own subfolder holding
one JSON+CSV pair per variance run (`<tool>_run<N>_<timestamp>.*`) plus a single
`variance.json` (mean ± std F1 across runs).

Every run writes two files that share a timestamped stem:

```
<tool>_<timestamp>.json   full detail: metrics + per-contract breakdown
<tool>_<timestamp>.csv     one row per contract, spreadsheet-friendly
```

## Filename stem by phase

| Phase | Folder | Example stem |
|---|---|---|
| 0 | `phase0_traditional/` | `slither_20260606T154745Z`, `mythril_...` |
| 1 | `phase1_single_llm/` | `gpt4o_chain_of_thought_...`, `gpt41-nano_chain_of_thought_...` |
| 2 | `phase2_critique/` | `critique_gpt4o-mini_to_gpt4o_chain_of_thought_...` |
| 3 | `phase3_multi_agent/<run-name>/` | `multiagent_gpt4o-mini_run1_...` (+ `variance.json`) |
| 4 | `phase4_hybrid/<run-name>/` | `hybrid_slither_gpt4o-mini_run1_...` (+ `variance.json`) |

## What's inside

- **All phases (JSON):** per-class TP/FP/FN, precision, recall, F1, micro/macro
  averages, runtime, and a per-contract list of ground-truth vs predicted
  classes.
- **Phase 1 adds:** token counts (prompt/completion/total), prompt messages,
  and the model response per contract.
- **Phase 2 adds:** detector-vs-critic token split, cost-adjusted metrics
  (`cost_adjusted` block, `behavior_counts`, `agreed_rate`), and per-contract
  critic behaviour (`removed` / `added` / `agreed` and the ground-truth-classified
  `behavior` tags).
- **Phase 3 adds:** per-agent detail (each specialist + moderator: classes,
  tokens, runtime, raw response, errors), a `role_tokens` breakdown per contract
  and `role_token_totals` aggregate, the specialist union vs moderator final
  list, and a `variance.json` with per-run and mean ± std F1 (overall + per
  contract).
- **Phase 4 adds:** per-contract Slither in-scope findings (the LLM's input),
  the LLM's confirm/reject decision per finding + raw response, a `skipped_llm`
  flag (Slither found nothing → no LLM call) and tokens, plus run-level
  `skip_rate`, `confirmed_total`, `rejected_total`, and `variance.json`. The
  three-way comparison (Slither / LLM / hybrid) and false-positive-reduction
  numbers are produced on demand by `hybrid_behaviour.py` (not stored).

These files are generated artifacts — safe to delete and regenerate by re-running.
