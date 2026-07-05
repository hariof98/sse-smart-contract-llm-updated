# Phase 4 — Hybrid (LLM reviews Slither output)

**Question (RQ2):** Is an LLM+tool hybrid more cost-effective than either alone?
Specifically: can a cheap LLM (`gpt4o-mini`) filtering Slither's findings match
or beat an expensive LLM (`gpt4o`) working alone — and at what cost ratio?

## What it does

```
cached Slither findings ──(keep in-scope)──▶ LLM reviews each (confirm / reject) ──▶ confirmed = final
        (Phase 0, not re-run)                  (single call; skipped if nothing in scope)
```

The LLM is a **filter**, not a new analyser:

- It reads Slither's in-scope findings + the contract, and marks each finding
  **confirmed** or **rejected**.
- The final prediction is the **confirmed** subset only.
- It **may NOT add** findings Slither didn't report (filter-only, no
  augmentation — enforced in code and stated in the prompt).

**Slither is never re-run** — the tool reads the cached Phase 0 result
(`results/phase0_traditional/slither_*.json`). The Slither detector→class
mapping (`DETECTOR_TO_CLASS`) and the LLM API client (`call_chat`) are reused
from Phase 0 / Phase 1, not duplicated.

**Efficiency property:** if Slither reported zero in-scope findings for a
contract, the LLM call is **skipped** (tokens = 0). That skip is a real cost
saving and is measured (skip rate).

## Contents

| File                            | What it does                                                                                                                                       |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run.py`                        | Entry point. Runs the hybrid `--runs` times for variance; writes per-run JSON + CSV and `variance.json` under `results/phase4_hybrid/<run-name>/`. |
| `tools/llm_hybrid.py`           | Reads cached Slither findings, filters to in-scope, skips empties, single LLM confirm/reject call, builds the confirmed prediction.                |
| `prompts/filter_review.py`      | The confirm/reject filter prompt (fixed; states the no-augmentation rule).                                                                         |
| `reporting/hybrid_logger.py`    | Writes results with Slither input, per-finding decisions, skip flag, tokens.                                                                       |
| `reporting/hybrid_behaviour.py` | Offline analysis: 3-way comparison, skip rate, false-positive reduction. No API calls.                                                             |
| `run_configs.py`                | The three prepared configs (primary mini hybrid, gpt4o-alone data-reuse reference, gpt4o hybrid ablation).                                         |

## Command reference

Run from the **project root** (needs `GITHUB_TOKEN` in `.env`, and a cached
Phase 0 Slither result — run Phase 0 first if you don't have one).

**Master command** (runs the full phase):

```bash
python3 -m phases.phase4_hybrid.run --model gpt4o-mini
python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name hybrid_slither_gpt4o-mini --model gpt4o-mini
```

Other commands:

```bash
python3 -m phases.phase4_hybrid.run --model gpt4o                         # strong-LLM hybrid
python3 -m phases.phase4_hybrid.run --config primary_mini_hybrid          # a prepared config
python3 -m phases.phase4_hybrid.run --model gpt4o-mini --dry-run          # first 3 contracts, nothing saved
python3 -m phases.phase4_hybrid.run --slither-results results/phase0_traditional/slither_<ts>.json

# List the prepared run configs:
python3 -m phases.phase4_hybrid.run_configs

# Analyse a saved run (3-way comparison, skip rate, FP reduction), no API calls:
python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name hybrid_slither_gpt4o-mini --model gpt4o-mini
python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name hybrid_slither_gpt4o-mini --model gpt4o-mini --compare-llm-model gpt4o
```

### CLI arguments (`run.py`)

| Flag                | Default                                       | Meaning                                                                      |
| ------------------- | --------------------------------------------- | ---------------------------------------------------------------------------- |
| `--model`           | `gpt4o-mini` (from `shared/config/models.py`) | LLM that reviews Slither findings.                                           |
| `--dataset`         | `smartbugs`                                   | `smartbugs`, `solidifi` (if a loader exists), or a path to a `dataset/` dir. |
| `--runs`            | `3`                                           | Full runs for variance (mean ± std F1).                                      |
| `--run-name`        | tool name                                     | Output subfolder under `results/phase4_hybrid/`.                             |
| `--slither-results` | newest                                        | Path to the cached Phase 0 `slither_*.json` to filter.                       |
| `--config`          | —                                             | Load a prepared config from `run_configs.py`.                                |
| `--dry-run`         | off                                           | First 3 contracts, nothing saved.                                            |

## Prepared experiment runs

See `run_configs.py`:

1. **`primary_mini_hybrid`** — `gpt4o-mini` + Slither, budget-matched to the
   Phase 1 `gpt4o-mini` single-agent. **Fill `BUDGET_MATCH_TARGET_TOKENS`** from
   `results/phase1_single_llm/gpt4o-mini_*.json` → `total_tokens_used`.
2. **`comparison_gpt4o_single`** — DATA REUSE, no new run. Points the analysis at
   the existing Phase 1 `gpt4o` results as the "LLM alone (strong)" comparison.
3. **`ablation_gpt4o_hybrid`** — `gpt4o` + Slither, uncapped. Does the hybrid
   still help with a strong LLM, or is the value in cheap models?

## What to report (non-negotiable for the write-up)

1. **Three-way comparison table** — Slither alone / LLM alone / hybrid, with
   precision, recall, F1, tokens, cost per contract. From `hybrid_behaviour.py`.
2. **Skip rate** — % of contracts where Slither found nothing in scope and the
   hybrid saved an LLM call. The concrete efficiency gain.
3. **False-positive reduction** — how many Slither findings the LLM correctly
   rejected (checked vs ground truth). Where the hybrid should win, since
   Slither is known for false positives.
4. **Cost substitution finding** — does `gpt4o-mini` + Slither match/exceed
   `gpt4o` alone on F1, and at what token ratio? The primary RQ2 answer.
5. **Mean and std of F1 across the `--runs` runs** — in `variance.json`.

## Determinism

Temperature is 0 (in the shared `call_chat`); the client exposes no seed, so
variance is measured over `--runs` (default 3). Note: the Slither _input_ is
fixed (cached), so any run-to-run variation comes only from the LLM's review.

## Depends on

`shared/core`, `shared/datasets`, `shared/config/models`, Phase 0's
`slither_tool.DETECTOR_TO_CLASS` + its cached results, and Phase 1's `call_chat`

- `attach_raw_metadata` — all reused, not duplicated. See `docs/PHASE4.md`.
