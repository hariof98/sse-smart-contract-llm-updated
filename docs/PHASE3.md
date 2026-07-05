# Phase 3 — Multi-Agent Architecture

## What Phase 3 is

A role-specialised multi-agent pipeline that reuses the Phase 1 infrastructure:

```
                   ┌─▶ reentrancy specialist    ─┐
contract source ───┼─▶ access_control specialist ─┼─▶ moderator ─▶ final classes
                   └─▶ timestamp specialist      ─┘
                        (parallel, isolated)         (sequential)
```

Three specialist agents each own exactly one vulnerability class, plus a
moderator that aggregates them.

Design choices that define this phase (locked):
- **Same model for all four agents.** Specialisation is by **system prompt
  only** — no per-specialist models, no class-specific few-shot examples.
- **Specialists run in parallel** with **no cross-visibility** — each sees only
  the contract source, never another specialist's output.
- **Moderator runs sequentially** after all specialists complete. It receives
  the contract source plus all three specialist outputs and produces the final
  list: aggregate, deduplicate, arbitrate conflicts, and (only if strongly
  justified) add a class no specialist reported.
- **Determinism:** temperature 0; the shared client exposes no seed, so
  variance is measured empirically over three runs per contract.

## The research question (RQ4)

> Does the added complexity of a multi-agent design justify itself? More agents
> means more inference cost and more engineering overhead. If a single
> well-prompted model achieves comparable results, the case for orchestration
> weakens.

Phase 2 answered this for a 2-agent detector→critic pipeline. Phase 3 answers it
for a **role-specialised** design, and adds a sharper sub-question: does splitting
the task by vulnerability class actually make each specialist better at its own
class than a generalist single agent? Hence **per-specialist recall** is a
first-class output, alongside cost-adjusted F1.

## How it plugs in (no harness changes)

`tools/llm_multi_agent.py` calls three specialists (in a thread pool) then the
moderator, but from the harness's view it is still one tool with one
`run(contract_path) -> Prediction`. The scorer, runner, and core logger are
unchanged. The API client, token counting, and JSON parsing are reused from
Phase 1's `llm_single_agent` (`call_chat`), not duplicated.

| Concern | Where it lives |
|---|---|
| Specialist + moderator orchestration | `tools/llm_multi_agent.py` |
| Specialist prompts (fixed) | `prompts/{reentrancy,access_control,timestamp}_specialist.py` |
| Moderator prompt (fixed) | `prompts/moderator.py` |
| Shared API call + token counting | `phases/phase1_single_llm/tools/llm_single_agent.py` (`call_chat`) |
| Per-agent cost + behaviour logging | `reporting/multi_agent_logger.py` |
| Moderator behaviour analysis | `reporting/moderator_behaviour.py` |
| Entry point | `phases/phase3_multi_agent/run.py` |

## Experimental matrix (prepared in `run_configs.py`)

| Run | Model | Token cap | Moderator | Specialists | Purpose |
|---|---|---|---|---|---|
| `budget_matched_mini` | `gpt4o-mini` | **placeholder** | on | all 3 | Cost baseline for RQ4 — budget-matched to Phase 2's best run. |
| `uncapped_gpt4o` | `gpt4o` | uncapped | on | all 3 | Quality upper bound. |
| `ablation_no_moderator` | `gpt4o-mini` | 20000 | **off** | all 3 | Isolates the moderator: final = deduped union of specialists. |
| `ablation_two_specialists` | `gpt4o-mini` | 20000 | on | reentrancy + access_control | Drops the timestamp specialist (smallest class). |

> **Placeholder:** `budget_matched_mini` intentionally has `token_cap = None`.
> Fill `BUDGET_MATCHED_TOKEN_CAP` in `run_configs.py` from Phase 2's best-run
> `total_tokens_used` before running it.

## Commands

```bash
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini
python3 -m phases.phase3_multi_agent.run --model gpt4o --token-cap 0
python3 -m phases.phase3_multi_agent.run --config ablation_no_moderator
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini --dry-run
python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour --run-name <name>
```

Requires `GITHUB_TOKEN` in `.env` (see `SETUP.md`).

## What Phase 3 measures (beyond P/R/F1)

### 1. Cost by agent role (central, not optional)
Four calls per contract. The tool logs per-call tokens and runtime; results
carry a `role_tokens` breakdown (each specialist + moderator) per contract and a
`role_token_totals` aggregate. Without this the cost dimension of RQ4 cannot be
answered.

### 2. Per-specialist recall
`moderator_behaviour.py` computes each specialist's recall on its own class
against ground truth. This is the specialisation test: a specialist that does
not beat the Phase 1 single agent on its own class is not earning its keep.

### 3. Moderator behaviour
Aggregated across all contracts and runs:

| Tag | Meaning |
|---|---|
| `kept` | specialist finding the moderator retained |
| `dropped` | specialist finding the moderator removed |
| `added` | moderator finding no specialist reported |
| `merged` | duplicate specialist findings collapsed |
| override rate | `(dropped + added) / specialist findings` — how much the moderator changed |

If the override rate exceeds ~50%, the specialists are not contributing and the
moderator is effectively doing the whole job alone.

### 4. Variance discipline
Three runs per contract (`--runs 3`). `variance.json` records per-run micro-F1
plus mean ± std overall and per contract, so the Phase 1/2 → Phase 3 delta is a
real signal and not noise.

## Graceful degradation & limits

- A failed specialist call is logged and treated as empty findings; the
  moderator still runs on the survivors.
- A failed moderator call falls back to the specialist union (recorded with
  `fell_back_to_union: true`).
- A contract whose source alone exceeds the token cap is skipped and returns an
  empty Prediction with the reason recorded (`skipped: true`). The token
  estimate is a ~4-chars/token heuristic, since the shared client exposes no
  tokenizer and Phase 3 does not modify shared plumbing.

## Risks to watch (and report)

- **Moderator does everything.** High override rate → specialists aren't
  contributing; the design collapses to a single agent with extra cost.
- **Specialists over-report their own class.** A specialist told to find class X
  may see X everywhere (precision drops); the moderator must prune it.
- **Specialisation buys nothing.** If per-specialist recall ≈ single-agent
  recall, the split adds cost without benefit — a clean negative RQ4 finding.
- **Cost blow-up.** Four calls per contract vs one (Phase 1) / two (Phase 2).
  Cost-adjusted F1 is the honest comparison.

## Done when

- The four configs run on SmartBugs Curated (SolidiFI later — the pipeline is
  dataset-agnostic).
- Per-class P/R/F1 with mean ± std across three runs.
- Token breakdown by agent role, and cost-adjusted F1 vs Phase 1 & Phase 2.
- Moderator behaviour breakdown + per-specialist recall.
- Either a config beats the Phase 1/Phase 2 baselines on cost-adjusted F1, **or**
  a clear negative finding is documented.

## Current status

Pipeline, prompts, runner, logger, analysis, and run configs are implemented and
wired end-to-end. Full runs are pending GitHub Models quota (the free tier has
been rate-limited during development). Use `--dry-run` to verify wiring; run the
matrix once quota is available and after filling the budget-matched token cap.
