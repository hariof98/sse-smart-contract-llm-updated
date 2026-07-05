# Phase 4 — Hybrid Architecture (LLM reviews Slither output)

## What Phase 4 is

A hybrid pipeline where an LLM acts as a **filter** over a traditional tool's
output, reusing earlier phases end-to-end:

```
       Phase 0 (cached)                     Phase 4
  Slither findings ──▶ keep in-scope ──▶ LLM review (confirm/reject) ──▶ confirmed = final
   (NOT re-run)          (DETECTOR_TO_CLASS)     (single call, skip if empty)
```

Design choices that define this phase (locked):
- **LLM as a filter, not an analyser.** For each Slither finding it outputs
  `confirmed` or `rejected`; the final prediction is the confirmed subset.
- **No augmentation.** The LLM may not add findings Slither didn't report —
  enforced in the prompt *and* in code (`_decisions` only counts classes that
  were in Slither's in-scope set).
- **Slither is cached, not re-run.** Findings come from the Phase 0
  `slither_*.json`; the Phase 0 `DETECTOR_TO_CLASS` mapping is reused.
- **Skip-empty efficiency.** If Slither found nothing in scope, no LLM call is
  made (tokens = 0). The skip rate is a first-class measured outcome.
- **Determinism:** temperature 0; the shared client exposes no seed, so variance
  is measured over three runs. The Slither input is fixed, so all run-to-run
  variation comes from the LLM review.

## The research question (RQ2)

> Is a hybrid (LLM + traditional tool) more cost-effective than either alone?

Slither is cheap and high-recall but noisy (many false positives). A strong LLM
alone is accurate but expensive. The hybrid bet: a **cheap** LLM only has to
*review* Slither's shortlist (a much smaller, cheaper task than open-ended
detection) and prune the false positives. If `gpt4o-mini + Slither` matches
`gpt4o` alone at a fraction of the tokens, that is a concrete cost-substitution
win — the core RQ2 result.

## How it plugs in (no harness changes)

`tools/llm_hybrid.py` reads cached Slither findings and makes at most one LLM
call, but from the harness's view it is still one tool with one
`run(contract_path) -> Prediction`. The scorer, runner, and core logger are
unchanged.

| Concern | Where it lives |
|---|---|
| Slither read + filter + LLM review | `tools/llm_hybrid.py` |
| Filter prompt (fixed) | `prompts/filter_review.py` |
| Reused Slither mapping | `phases/phase0_traditional/tools/slither_tool.py` (`DETECTOR_TO_CLASS`) |
| Reused LLM API client | `phases/phase1_single_llm/tools/llm_single_agent.py` (`call_chat`) |
| Per-finding logging | `reporting/hybrid_logger.py` |
| 3-way comparison / behaviour | `reporting/hybrid_behaviour.py` |
| Entry point | `phases/phase4_hybrid/run.py` |

## Experimental matrix (prepared in `run_configs.py`)

| Run | Model | Type | Purpose |
|---|---|---|---|
| `primary_mini_hybrid` | `gpt4o-mini` | run | Primary RQ2 run; budget-matched to Phase 1 gpt4o-mini (**placeholder token target**). |
| `comparison_gpt4o_single` | `gpt4o` | **data reuse** | No new run — reuse Phase 1 gpt4o single-agent as the "LLM alone (strong)" point. |
| `ablation_gpt4o_hybrid` | `gpt4o` | run | Does the hybrid still help with a strong LLM, or is the value in cheap models? |

> **Placeholder:** fill `BUDGET_MATCH_TARGET_TOKENS` in `run_configs.py` from the
> Phase 1 gpt4o-mini run's `total_tokens_used` (a reporting comparison target,
> not a hard cap — the hybrid naturally uses ≤1 call/contract).

## Commands

```bash
python3 -m phases.phase4_hybrid.run --model gpt4o-mini
python3 -m phases.phase4_hybrid.run --model gpt4o
python3 -m phases.phase4_hybrid.run --config primary_mini_hybrid
python3 -m phases.phase4_hybrid.run --model gpt4o-mini --dry-run
python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name hybrid_slither_gpt4o-mini --model gpt4o-mini
```

Requires `GITHUB_TOKEN` in `.env` and a cached Phase 0 Slither result. If none
exists: `python3 -m phases.phase0_traditional.run --tool slither`.

## What Phase 4 measures (beyond P/R/F1)

### 1. Three-way comparison (central to RQ2)
`hybrid_behaviour.py` prints precision / recall / F1 / tokens / tokens-per-
contract for **Slither alone** (Phase 0), **LLM alone** (Phase 1, same or a
specified model), and **Slither + LLM hybrid** (Phase 4). Without this the
cost-effectiveness question cannot be answered.

### 2. Skip rate
% of contracts where Slither found nothing in scope, so the hybrid made no LLM
call at all. This is the pattern's concrete efficiency gain.

### 3. False-positive reduction
How many Slither findings the LLM **correctly rejected** (checked against ground
truth), vs how many true positives it **wrongly rejected**. Slither's weakness is
false positives, so this is where the hybrid should win most.

### 4. Cost substitution
Does `gpt4o-mini + Slither` match/exceed `gpt4o` alone on F1, and at what token
ratio? The primary RQ2 read-out (printed at the end of `hybrid_behaviour.py`).

### 5. Variance discipline
Three runs (`--runs 3`); `variance.json` records per-run and mean ± std F1
(overall + per contract).

## Risks to watch (and report)

- **LLM over-prunes.** It rejects real bugs (rising `tp_rejected`) → recall
  drops below Slither alone. The hybrid must cut FPs without cutting TPs.
- **LLM rubber-stamps.** It confirms everything → precision no better than
  Slither alone; the filter added cost for nothing.
- **Ceiling from Slither recall.** Filter-only means the hybrid can never exceed
  Slither's recall (it can't add missed bugs). If Slither missed a class, the
  hybrid misses it too — a structural limit worth stating.
- **Skit-rate confound.** A high skip rate lowers cost but only helps F1 if those
  contracts were truly negative; check skips against ground truth.

## Done when

- Primary + ablation hybrid runs on SmartBugs Curated, with the gpt4o Phase 1
  reuse as the strong-LLM comparison.
- Three-way comparison table (P/R/F1/tokens/cost) with mean ± std across runs.
- Skip rate and false-positive-reduction numbers.
- A clear cost-substitution verdict for RQ2 (hybrid matches strong LLM at lower
  cost — or a documented negative finding).

## Current status

Tool, prompt, runner, logger, analysis, and run configs are implemented and
wired end-to-end. Full runs are pending GitHub Models quota. Use `--dry-run` to
verify wiring; run the matrix once quota is available and after filling the
budget-match target.
