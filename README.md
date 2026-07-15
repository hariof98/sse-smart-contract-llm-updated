# Practicum — Evaluating LLMs for Smart Contract Vulnerability Detection

An evaluation harness that compares **traditional tools** (Slither, Mythril),
**single LLMs** (Phase 1), **two-agent LLM critique pipelines** (Phase 2),
**multi-agent specialist+moderator pipelines** (Phase 3), and **LLM+tool hybrids**
(Phase 4) on the same Solidity vulnerability-detection task — using the same
dataset and the same metrics so results are directly comparable. Cost (tokens and
US-dollar estimates) is treated as a first-class axis alongside accuracy, because
multi-call, agentic pipelines multiply the token bill for every contract.

## Research questions

The project is organised around four research questions, each mapped to the
phases that answer it:

- **RQ1 — Generalisation & continuous prompt improvement.** How well do older and
  newer LLMs, and different architectures, generalise across datasets and project
  types, and how does systematic continuous prompt improvement influence
  performance? *(Partially addressed; the cross-dataset and prompt-improvement
  components are future work.)*
- **RQ2 — Hybrid cost-effectiveness.** Is an LLM-guided hybrid (an LLM filtering a
  static analyser's output) more cost-effective than standalone LLM
  classification? → **Phase 4**
- **RQ3 — Practical usability.** How do LLM-based detectors compare with
  traditional tools in detection rate and false positives? → **Phases 0–1**
- **RQ4 — Automated critiquing & multi-agent design.** How do critiquing and
  multi-agent architectures affect accuracy and cost compared with a single-agent
  LLM, and what trade-offs arise? → **Phases 2–3**

## The core idea — one pluggable interface

Every detector, no matter how complex, plugs in by implementing a single
function:

```python
def run(contract_path: str) -> Prediction
```

The shared harness (`shared/core/`) runs that function over every contract, scores
the predictions against ground truth, and logs precision / recall / F1, runtime,
and (for LLMs) tokens and cost. Adding a new tool never requires touching the
scorer, runner, or logger — the architecture under test is the only thing that
changes between phases.

## The phases

Each phase is a self-contained package that reuses the same harness, LLM client,
and prompt convention. A phase differs from its neighbours only in *how many*
LLM calls it makes and *how* it combines them.

| Phase | What it does                                                             | RQ  | Code                          | Docs             |
| ----- | ----------------------------------------------------------------------- | --- | ----------------------------- | ---------------- |
| **0** | Traditional static/symbolic baseline (Slither, Mythril).                | RQ3 | `phases/phase0_traditional/`  | `docs/PHASE0.md` |
| **1** | A single LLM classifies each contract under one fixed prompt.           | RQ3 | `phases/phase1_single_llm/`   | `docs/PHASE1.md` |
| **2** | A detector LLM's findings are reviewed by a second "critic" LLM.        | RQ4 | `phases/phase2_critique/`     | `docs/PHASE2.md` |
| **3** | Three class-specialist LLMs run in parallel; a moderator arbitrates.    | RQ4 | `phases/phase3_multi_agent/`  | `docs/PHASE3.md` |
| **4** | An LLM confirms/rejects a cached Slither run's findings (a filter).     | RQ2 | `phases/phase4_hybrid/`       | `docs/PHASE4.md` |

## Codebase structure

```
practicum/
├── phases/                       # one self-contained folder per phase
│   ├── phase0_traditional/         Slither / Mythril baseline
│   │   ├── run.py                    entry point
│   │   ├── tools/                    slither_tool, mythril_tool
│   │   └── README.md
│   ├── phase1_single_llm/          single-LLM detection
│   │   ├── run.py                    entry point
│   │   ├── tools/                    llm_single_agent (+ shared LLM plumbing)
│   │   ├── prompts/                  zero_shot, few_shot, chain_of_thought
│   │   ├── reporting/                llm_logger
│   │   └── README.md
│   ├── phase2_critique/            two-agent detector → critic
│   │   ├── run.py                    entry point
│   │   ├── tools/                    llm_critique
│   │   ├── prompts/                  critique
│   │   ├── reporting/                critique_logger, critique_compare
│   │   └── README.md
│   ├── phase3_multi_agent/         three specialists + moderator
│   │   ├── run.py                    entry point (multi-run variance)
│   │   ├── tools/                    llm_multi_agent
│   │   ├── prompts/                  3 specialists + moderator
│   │   ├── reporting/                multi_agent_logger, moderator_behaviour
│   │   ├── run_configs.py            prepared experiment configs
│   │   └── README.md
│   └── phase4_hybrid/              LLM filters Slither's output
│       ├── run.py                    entry point (multi-run variance)
│       ├── tools/                    llm_hybrid
│       ├── prompts/                  filter_review
│       ├── reporting/                hybrid_logger, hybrid_behaviour
│       ├── run_configs.py            prepared experiment configs
│       └── README.md
│
├── shared/                       # used by ALL phases (stable harness)
│   ├── config/                     models.py — model catalogue + GitHub/OpenAI provider toggle
│   ├── core/                       schema (Prediction), runner, scorer, logger
│   └── datasets/                   smartbugs_loader + the SmartBugs Curated data
│
├── docs/                         # per-phase design docs + metrics glossary + setup + PROJECT_STRUCTURE.md
├── tests/                        # standalone checks (dataset loader)
├── examples/                     # small runnable demos
└── results/                      # JSON + CSV output, one pair per run
```

Each phase folder (and `shared/`) has its own `README.md`. For a full map of the
codebase see `docs/PROJECT_STRUCTURE.md`; for setup and API keys see
`docs/SETUP.md`.

## Model provider & configuration

All model choices live in one file — `shared/config/models.py`. A single
`USE_OPENAI` flag selects the backend, and only the models for the active
provider are valid:

| `USE_OPENAI` | Provider              | Key in `.env`    | Models available (default in **bold**) |
| ------------ | --------------------- | ---------------- | -------------------------------------- |
| `False`      | GitHub Models (free)  | `GITHUB_TOKEN`   | **`gpt-4o-mini`**, `gpt-4o`            |
| `True`       | OpenAI API (paid)     | `OPENAI_API_KEY` | **`gpt-4.1-nano`**, `gpt-5.5`, `o3`    |

The same file holds the per-phase default model (`PHASE1_MODEL`,
`PHASE2_DETECTOR`, `PHASE2_CRITIC`, `PHASE3_MODEL`, `PHASE4_MODEL`), which are
provider-aware. All LLM phases share one client (`call_chat`) and one robust
JSON parser, so provider quirks (reasoning-model token limits, prose-wrapped
output) are handled once and inherited everywhere.

## Dataset & scope

- **Dataset:** SmartBugs Curated (54 in-scope contracts).
- **Vulnerability classes:** `reentrancy`, `access_control`, `timestamp_dependency`.
- **Matching:** class-only (a prediction matches if it names the right class for
  the contract).
- **Variance:** temperature is pinned to 0 and multi-call phases (3–4) are run
  three times, reporting mean ± std F1.

See `docs/METRICS_GLOSSARY.md` for definitions of every metric (TP/FP/FN,
precision, recall, F1, micro vs macro, cost-adjusted F1).

## Latest results (OpenAI API runs)

Micro-F1 on the 54-contract subset (three classes). The LLM phases were run on
the paid OpenAI provider (`USE_OPENAI = True`); Phases 3–4 report the mean over
three runs. Tokens are the directly logged counts.

| Phase | Configuration                     | Micro-F1      | Tokens        | Notes                              |
| ----- | --------------------------------- | ------------- | ------------- | ---------------------------------- |
| 0     | Slither                           | 0.721         | 0             | fast rule-based baseline           |
| 0     | Mythril                           | 0.614         | 0             | ~60.6 s/contract                   |
| 1     | single LLM — `o3`                 | 0.809         | 85k           | best single model                  |
| 1     | single LLM — `gpt-4.1-nano`       | 0.807         | 66k           | cheapest, still beats both tools   |
| 1     | single LLM — `gpt-5.5`            | 0.800         | 85k           |                                    |
| 2     | detector→critic (`gpt-5.5`→`o3`)  | 0.794         | 215k          | 90.7% agreement; ~net-neutral F1   |
| 3     | multi-agent — `gpt-5.5`           | 0.853 ± 0.010 | 903k (3 runs) | **best F1 overall**, priciest      |
| 3     | multi-agent — `gpt-4.1-nano`      | 0.670 ± 0.003 | 618k (3 runs) | weak model degrades below single   |
| 4     | hybrid — `gpt-4.1-nano`           | 0.795 ± 0.006 | 48k/run       | stable & cheap; skips 18.5%        |
| 4     | hybrid — `o3`                     | 0.772 ± 0.011 | 63k/run       | ceiling is Slither's recall        |

**Takeaways.** A single LLM already beats both traditional tools through higher
recall, at every tier. The specialist+moderator multi-agent design gives the best
F1 — but only with a capable model, and at the highest token cost (it degrades a
weak model). Cross-model critique, once both models are strong, defers to the
detector ~90% of the time and barely moves F1. The hybrid delivers
better-than-tool accuracy at the lowest marginal cost. No architecture wins on
both accuracy and cost, so the practical answer is a **routing strategy** rather
than a single detector.
