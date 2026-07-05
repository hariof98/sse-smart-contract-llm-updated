# Phase 3 — Multi-Agent (Specialists + Moderator)

**Question (RQ4):** Does a role-specialised multi-agent design (three per-class
specialists + a moderator) beat a single agent — and does it justify its extra
cost? Reported with **cost-adjusted** metrics and per-specialist recall, not raw
F1 alone.

## What it does

```
contract ─▶ reentrancy specialist    ┐
         ─▶ access_control specialist ┼─ (parallel, no cross-visibility) ─▶ moderator ─▶ final classes
         ─▶ timestamp specialist      ┘                                    (sequential)
```

- **Specialisation is by system prompt only.** All four agents use the SAME
  model in a given run — no per-specialist models, no per-class few-shot.
- **Specialists run in parallel** and each sees only the contract source (never
  each other's output). Each returns findings for its assigned class only.
- **The moderator runs after** the specialists, sees the contract plus all three
  specialist outputs verbatim, and produces the final list (aggregate,
  deduplicate, arbitrate, optionally add a strongly-justified class).

To the harness this is still one tool with one `run(contract_path) -> Prediction`,
so `shared/core` (schema/runner/scorer/logger) is untouched. The API client,
token counting, and parsing plumbing are **reused** from Phase 1's
`llm_single_agent` (`call_chat`), not duplicated.

## Contents

| File                                   | What it does                                                                                                                                                 |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `run.py`                               | Entry point. Runs the pipeline `--runs` times for variance; writes per-run JSON + CSV and a `variance.json` under `results/phase3_multi_agent/<run-name>/`.  |
| `tools/llm_multi_agent.py`             | The pipeline: parallel specialists → sequential moderator. Graceful degradation, per-contract token cap, logs every agent's raw response + tokens + runtime. |
| `prompts/reentrancy_specialist.py`     | Reentrancy-only system prompt.                                                                                                                               |
| `prompts/access_control_specialist.py` | Access-control-only system prompt.                                                                                                                           |
| `prompts/timestamp_specialist.py`      | Timestamp-dependency-only system prompt.                                                                                                                     |
| `prompts/moderator.py`                 | Moderator aggregation/arbitration prompt.                                                                                                                    |
| `reporting/multi_agent_logger.py`      | Writes results with per-agent tokens/runtime/raw responses + role-token breakdown.                                                                           |
| `reporting/moderator_behaviour.py`     | Offline analysis: kept/dropped/added/merged, override rate, per-specialist recall. No API calls.                                                             |
| `run_configs.py`                       | The four prepared experiment configs (budget-matched mini, uncapped gpt4o, two ablations). Not auto-executed.                                                |

## Command reference

Run from the **project root** (needs `GITHUB_TOKEN` in `.env`).

**Master command** (runs the full phase):

```bash
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini
```

Other commands:

```bash
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini --runs 1         # runs ony 1 time instead of 3
python3 -m phases.phase3_multi_agent.run --model gpt4o --token-cap 0         # uncapped
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini --no-moderator   # union ablation
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini --specialists reentrancy,access_control
python3 -m phases.phase3_multi_agent.run --config ablation_no_moderator      # a prepared config
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini --dry-run        # first 3 contracts, nothing saved

# List the prepared run configs:
python3 -m phases.phase3_multi_agent.run_configs

# Analyse a saved run (override rate + per-specialist recall), no API calls:
python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour --run-name <name>
```

### CLI arguments (`run.py`)

| Flag             | Default                                       | Meaning                                                                      |
| ---------------- | --------------------------------------------- | ---------------------------------------------------------------------------- |
| `--model`        | `gpt4o-mini` (from `shared/config/models.py`) | Model for all four agents.                                                   |
| `--dataset`      | `smartbugs`                                   | `smartbugs`, `solidifi` (if a loader exists), or a path to a `dataset/` dir. |
| `--runs`         | `3`                                           | Full runs for variance (mean ± std F1).                                      |
| `--run-name`     | tool name                                     | Output subfolder under `results/phase3_multi_agent/`.                        |
| `--token-cap`    | `20000`                                       | Per-contract source token cap; `0` = uncapped.                               |
| `--no-moderator` | off                                           | Ablation: final = deduped union of specialists.                              |
| `--specialists`  | all three                                     | Comma-separated subset (e.g. drop `timestamp_dependency`).                   |
| `--config`       | —                                             | Load a prepared config from `run_configs.py` (overrides tuning flags).       |
| `--dry-run`      | off                                           | First 3 contracts, nothing saved.                                            |

## Prepared experiment runs

See `run_configs.py`. **`budget_matched_mini` has a placeholder token cap** —
fill `BUDGET_MATCHED_TOKEN_CAP` from Phase 2's best-run total token budget
(`results/phase2_critique/*.json` → `total_tokens_used`) before running it.

## What to report (non-negotiable for the write-up)

1. **Tokens per contract by agent role** — three specialists + moderator. In
   every run summary, per-contract JSON (`role_tokens`), and `variance.json`.
2. **Per-specialist recall** — from `moderator_behaviour.py`. If the reentrancy
   specialist doesn't beat the Phase 1 single agent on reentrancy, class
   specialisation isn't working even if overall F1 looks fine.
3. **Moderator override rate** — from `moderator_behaviour.py`. If the moderator
   changes > ~50% of specialist findings, the specialists aren't contributing.
4. **Mean and std of F1 across the `--runs` runs** — overall and per contract,
   in `variance.json` and the run summary.

## Determinism & why it runs 3 times

Temperature is 0 (set in the shared `call_chat`), but the GitHub Models client
does not expose a fixed seed, and Phase 3 must not modify shared plumbing — so
the model can still give slightly different answers on the same contract.

That is why the pipeline runs the whole dataset **`--runs` times (default 3)**:
a single pass is one possibly-lucky number, so instead we report **mean ± std of
F1** across the runs (written to `variance.json`, overall and per contract).
This is a required write-up output, not an accident.

Cost note: each contract makes 4 calls (3 specialists + moderator), so a full
run is `contracts × 4 × runs` calls (e.g. `54 × 4 × 3 = 648`). To do a quick
single pass and save quota, use `--runs 1` (std will be 0 — fine for testing,
not for final numbers).

## Depends on

`shared/core`, `shared/datasets`, `shared/config/models`, and Phase 1's
`tools/llm_single_agent` (`call_chat`) + `reporting/llm_logger`
(`attach_raw_metadata`) — reused, not duplicated. See `docs/PHASE3.md`.
