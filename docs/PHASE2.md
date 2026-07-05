# Phase 2 — Two-Agent Critique Pipeline

## What Phase 2 is

A two-step pipeline that reuses the Phase 1 infrastructure:

```
contract  →  Detector LLM  →  (classes + reasoning)  →  Critic LLM  →  final classes
   │                                                                        │
   └──────────────────  contract source available to both  ────────────────┘
```

The detector and critic are **different models** (cross-model critique). The
critic sees the contract, the detector's reported vulnerability classes, and
the detector's full reasoning, and returns a revised list. That revised list
is the final prediction that gets scored.

Design choices that define this phase:
- **Cross-model** (critic ≠ detector).
- **Single round** (one critic pass, no back-and-forth).
- **No external grounding** (no docs/tools beyond the contract source).

This is the sharpest setup for isolating one question.

## The research question (RQ4)

> Does the added complexity of a multi-agent design justify itself? More agents
> means more inference cost and more engineering overhead. If a single
> well-prompted model achieves comparable results, the case for orchestration
> weakens.

Phase 2 answers this for the simplest case — a 2-agent pipeline — by comparing
against the best Phase 1 single-agent **at equal total cost**. So the headline
metric is not raw F1 but **cost-adjusted F1** (F1 per dollar, F1 per 1k tokens).

- If a Phase 2 config beats the Phase 1 baseline on cost-adjusted F1 → critique
  pays off.
- If it doesn't → that's a clean, publishable negative finding (most papers in
  the lit review never report cost-adjusted numbers at all).

## How it plugs in (no harness changes)

Phase 0 established that every tool is just `run(contract_path) -> Prediction`.
`tools/llm_critique.py` internally calls the detector then the critic, but from
the harness's view it is still one tool with one `run()`. The scorer, runner,
and core logger are unchanged.

| Concern | Where it lives |
|---|---|
| Detector + critic orchestration | `tools/llm_critique.py` |
| Critic prompt (fixed) | `prompts/critique.py` |
| Shared API call + parsing | `tools/llm_single_agent.py` (`call_chat`, `parse_vulnerabilities`) |
| Cost + behaviour logging | `reporting/critique_logger.py` |
| Entry point | `run_phase2.py` |

## Experimental matrix

| Run | Detector | Critic | Purpose |
|---|---|---|---|
| Baseline (Phase 1) | best single model | — | reference point |
| Cheap → Strong | `gpt4o-mini` | `gpt4o` / `gpt41` | "escalation" pattern |
| Strong → Cheap | `gpt4o` / `gpt41` | `gpt4o-mini` | "audit" pattern |
| Strong → Strong | `gpt4o` | `gpt41` | upper bound |

The asymmetry between Cheap→Strong and Strong→Cheap is the interesting result.
If Cheap→Strong matches the strong single-agent at lower cost, that's a
cheap-critique pattern worth writing about.

## Commands

```bash
python3 run_phase2.py --detector gpt4o-mini --critic gpt4o      # cheap -> strong
python3 run_phase2.py --detector gpt4o       --critic gpt4o-mini # strong -> cheap
python3 run_phase2.py --detector gpt4o       --critic gpt41      # strong -> strong
python3 run_phase2.py --detector gpt4o-mini --critic gpt4o --dry-run   # 3 contracts
```

Requires `GITHUB_TOKEN` in `.env` (see `SETUP.md`). The detector strategy
defaults to `chain_of_thought` because the critic needs reasoning to review.

## What Phase 2 measures (beyond P/R/F1)

### 1. Cost (central, not optional)
Critique doubles the API calls. Per contract the tool logs detector tokens,
critic tokens, total tokens, and latency. `run_phase2.py` reports
**tokens per true positive**, **F1 per 1k tokens**, and **F1 per dollar**.

### 2. Critic behaviour breakdown
For every contract the critic's edits are classified against ground truth:

| Tag | Meaning | Good/Bad |
|---|---|---|
| `fp_removed` | dropped a class not in ground truth | good |
| `tp_removed` | dropped a class that was in ground truth | bad |
| `tp_added` | added a class that was in ground truth | good |
| `fp_added` | added a class not in ground truth | bad |
| `agreed` | no change | — |

This shows *where* critique helps. Mostly `fp_removed` → the cheap-critic
pattern likely wins. Mostly `tp_added` → you need the strong critic.

### 3. Variance discipline
Carried over from Phase 1: temperature 0, fixed seed where available, multiple
runs per contract. Otherwise the Phase 1 → Phase 2 delta is just noise.

## Risks to watch (and report)

- **Critics agree too easily.** Watch `agreed_rate`. Above ~80% and the critic
  isn't doing meaningful work — strengthen the prompt before concluding
  "critique doesn't help".
- **Critics over-prune.** Recall drops while precision rises → the critic is too
  aggressive (rising `tp_removed`).
- **Confident-but-wrong reasoning fools the critic.** The critic sees the
  detector's reasoning; a convincing wrong chain can be rubber-stamped. Cases
  where the critic agreed with bad reasoning and produced a wrong final answer
  are worth reporting (the "decision + justification" trap from the lit review).
- **Shallow detector reasoning starves the critic.** The detector must produce
  detailed chain-of-thought, hence the `chain_of_thought` default.

## Done when

- Baseline + the three critique configs run on SmartBugs Curated (SolidiFI
  later — the pipeline is dataset-agnostic).
- Results table with per-class P/R/F1, total tokens, total cost.
- Behaviour breakdown (fp_removed / tp_removed / tp_added / agreed) per config.
- At least one config shown to beat the Phase 1 baseline on cost-adjusted F1,
  **or** a clear negative finding documented.

## Current status

Pipeline is implemented and wired end-to-end. Full runs are pending GitHub
Models quota (the free tier has been rate-limited during development). Use
`--dry-run` to verify wiring; run the full matrix once quota is available.
