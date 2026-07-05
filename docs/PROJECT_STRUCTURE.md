# Project Structure & Naming Reference

A single map of the codebase. It is organised **by phase**: each phase is a
self-contained folder under `phases/`, and everything shared by all phases
lives under `shared/`.

> Legend: **P0** = Phase 0 (traditional tools) · **P1** = Phase 1 (single LLM) ·
> **P2** = Phase 2 (detector → critic) · **P3** = Phase 3 (specialists +
> moderator) · **P4** = Phase 4 (LLM filters Slither). RQ1–RQ4 are the research
> questions from the practicum proposal.

---

## 1. Top-level tree

```
practicum/
│
├── phases/                         ONE SELF-CONTAINED FOLDER PER PHASE
│   │
│   ├── phase0_traditional/         [P0]  Slither / Mythril baseline — answers RQ3
│   │   ├── run.py                    entry point
│   │   ├── tools/
│   │   │   ├── slither_tool.py        Slither via subprocess
│   │   │   ├── mythril_tool.py        Mythril via Docker
│   │   │   └── patch_mythril_docker.sh
│   │   └── README.md
│   │
│   ├── phase1_single_llm/          [P1]  single-LLM detection — RQ3 + prompting (RQ1)
│   │   ├── run.py                    entry point
│   │   ├── tools/
│   │   │   └── llm_single_agent.py    LLM detector + shared LLM plumbing
│   │   ├── prompts/
│   │   │   ├── zero_shot.py
│   │   │   ├── few_shot.py
│   │   │   └── chain_of_thought.py    default (also feeds the P2 critic)
│   │   ├── reporting/
│   │   │   └── llm_logger.py          adds tokens / prompt / response
│   │   └── README.md
│   │
│   ├── phase2_critique/            [P2]  detector → critic — answers RQ4
│   │   ├── run.py                    entry point
│   │   ├── tools/
│   │   │   └── llm_critique.py        detector → critic pipeline
│   │   ├── prompts/
│   │   │   └── critique.py            the critic's review prompt
│   │   ├── reporting/
│   │   │   ├── critique_logger.py     adds cost + critic behaviour
│   │   │   └── critique_compare.py    re-scores detector vs after-critic
│   │   └── README.md
│   │
│   ├── phase3_multi_agent/         [P3]  specialists + moderator — answers RQ4
│   │   ├── run.py                    entry point (multi-run variance)
│   │   ├── tools/
│   │   │   └── llm_multi_agent.py     parallel specialists → sequential moderator
│   │   ├── prompts/
│   │   │   ├── reentrancy_specialist.py
│   │   │   ├── access_control_specialist.py
│   │   │   ├── timestamp_specialist.py
│   │   │   └── moderator.py           aggregation / arbitration prompt
│   │   ├── reporting/
│   │   │   ├── multi_agent_logger.py  per-agent tokens / runtime / raw responses
│   │   │   └── moderator_behaviour.py override rate + per-specialist recall
│   │   ├── run_configs.py            four prepared experiment configs
│   │   └── README.md
│   │
│   └── phase4_hybrid/              [P4]  LLM filters Slither output — answers RQ2
│       ├── run.py                    entry point (multi-run variance)
│       ├── tools/
│       │   └── llm_hybrid.py          reads cached Slither → LLM confirm/reject
│       ├── prompts/
│       │   └── filter_review.py       confirm/reject filter prompt (no augmentation)
│       ├── reporting/
│       │   ├── hybrid_logger.py       Slither input + per-finding decisions + skip flag
│       │   └── hybrid_behaviour.py    3-way comparison + skip rate + FP reduction
│       ├── run_configs.py            three prepared experiment configs
│       └── README.md
│
├── shared/                         USED BY ALL PHASES (stable harness)
│   ├── config/
│   │   └── models.py                 model catalog + per-phase model selection
│   ├── core/
│   │   ├── schema.py                 Vulnerability / GroundTruth / Prediction
│   │   ├── runner.py                 runs a tool over every contract
│   │   ├── scorer.py                 TP/FP/FN → precision / recall / F1
│   │   └── logger.py                 base JSON + CSV writer
│   ├── datasets/
│   │   ├── smartbugs_loader.py       folder name → class; returns GroundTruth[]
│   │   └── smartbugs-curated/        the actual .sol dataset (54 in-scope)
│   └── README.md
│
├── docs/                           documentation (this file, per-phase design, metrics, setup)
├── results/                        output — one JSON + one CSV per run (see §5)
├── tests/                          standalone checks (dataset loader)
└── examples/                       small runnable demos
```

---

## 2. Two zones: `phases/` and `shared/`

| Zone | Contains | Changes per tool? |
|---|---|---|
| `phases/phaseN_*/` | Everything specific to that phase: its entry point, tools, prompts, and reporting. | yes — this is where phases differ |
| `shared/core/` | Run + score + base-log. The plug-in harness. | **no — stable for all phases** |
| `shared/datasets/` | Provides `GroundTruth[]` from a dataset. | per dataset |

The one contract that ties it together:

```python
def run(contract_path: str) -> Prediction
```

Any detector that implements this (directly or via a `make_tool(...)` factory)
plugs into `shared.core.runner.run_evaluation` with no harness changes.

**Cross-phase reuse:** Phase 2 reuses Phase 1's LLM plumbing
(`phases.phase1_single_llm.tools.llm_single_agent`), the `chain_of_thought`
prompt, and `attach_raw_metadata` from Phase 1's logger — imported directly,
not duplicated. Phase 3 reuses the same `call_chat`. Phase 4 reuses `call_chat`
+ `attach_raw_metadata` (Phase 1) **and** the Slither detector→class mapping
`DETECTOR_TO_CLASS` (Phase 0), and reads Phase 0's cached results instead of
re-running Slither.

---

## 3. Phase → files map

### Phase 0 — Traditional tools  *(RQ3 baseline)*
| Concern | File |
|---|---|
| Entry point | `phases/phase0_traditional/run.py` |
| Slither / Mythril | `phases/phase0_traditional/tools/{slither,mythril}_tool.py` |
| Results writer | `shared/core/logger.py` |
| Design doc | `docs/PHASE0.md` |

### Phase 1 — Single LLM  *(RQ3 + prompting side of RQ1)*
| Concern | File |
|---|---|
| Entry point | `phases/phase1_single_llm/run.py` |
| Detector + shared LLM plumbing | `phases/phase1_single_llm/tools/llm_single_agent.py` |
| Prompting strategies | `phases/phase1_single_llm/prompts/{zero_shot,few_shot,chain_of_thought}.py` |
| Results writer | `phases/phase1_single_llm/reporting/llm_logger.py` |
| Design doc / summary | `docs/PHASE1.md`, `docs/PHASE1_SUMMARY.md` |

### Phase 2 — Detector → Critic  *(RQ4)*
| Concern | File |
|---|---|
| Entry point | `phases/phase2_critique/run.py` |
| Two-agent pipeline | `phases/phase2_critique/tools/llm_critique.py` |
| Critic prompt (fixed) | `phases/phase2_critique/prompts/critique.py` |
| Reused API call + parser | `phases/phase1_single_llm/tools/llm_single_agent.py` |
| Results writer | `phases/phase2_critique/reporting/critique_logger.py` |
| Detector-vs-critic re-analysis | `phases/phase2_critique/reporting/critique_compare.py` |
| Design doc | `docs/PHASE2.md` |

### Phase 3 — Specialists + Moderator  *(RQ4)*
| Concern | File |
|---|---|
| Entry point (multi-run variance) | `phases/phase3_multi_agent/run.py` |
| Multi-agent pipeline | `phases/phase3_multi_agent/tools/llm_multi_agent.py` |
| Specialist prompts (fixed) | `phases/phase3_multi_agent/prompts/{reentrancy,access_control,timestamp}_specialist.py` |
| Moderator prompt (fixed) | `phases/phase3_multi_agent/prompts/moderator.py` |
| Reused API call + token counting | `phases/phase1_single_llm/tools/llm_single_agent.py` (`call_chat`) |
| Results writer (per-agent detail) | `phases/phase3_multi_agent/reporting/multi_agent_logger.py` |
| Moderator behaviour / specialist recall | `phases/phase3_multi_agent/reporting/moderator_behaviour.py` |
| Prepared experiment configs | `phases/phase3_multi_agent/run_configs.py` |
| Design doc | `docs/PHASE3.md` |

### Phase 4 — Hybrid: LLM filters Slither  *(RQ2)*
| Concern | File |
|---|---|
| Entry point (multi-run variance) | `phases/phase4_hybrid/run.py` |
| Hybrid pipeline (Slither read → LLM filter) | `phases/phase4_hybrid/tools/llm_hybrid.py` |
| Filter prompt (fixed, no augmentation) | `phases/phase4_hybrid/prompts/filter_review.py` |
| Reused Slither mapping | `phases/phase0_traditional/tools/slither_tool.py` (`DETECTOR_TO_CLASS`) |
| Reused API call + token counting | `phases/phase1_single_llm/tools/llm_single_agent.py` (`call_chat`) |
| Results writer (Slither input + decisions + skip) | `phases/phase4_hybrid/reporting/hybrid_logger.py` |
| 3-way comparison / skip rate / FP reduction | `phases/phase4_hybrid/reporting/hybrid_behaviour.py` |
| Prepared experiment configs | `phases/phase4_hybrid/run_configs.py` |
| Design doc | `docs/PHASE4.md` |

---

## 4. Data flow (one run, end to end)

```
 shared/datasets/smartbugs_loader ──▶ load_smartbugs() → GroundTruth[]
                         │
                         ▼
 phases/phaseN/run.py ──▶ pick tool ──▶ phases/phaseN/tools/<tool>.run(contract) ──▶ Prediction
      │                                        ▲          │
      │              phases/phaseN/prompts/ ───┘          │ (LLM tools stash tokens /
      │                                                   │  reasoning in raw_output)
      ▼                                                   ▼
 shared/core/runner.run_evaluation(GroundTruth[], tool) ──▶ pairs (truth, prediction)
                         │
                         ▼
                 shared/core/scorer.score() ──▶ ScorerReport (P/R/F1, per-class + overall)
                         │
                         ▼
        shared/core/logger.log()                           ← Phase 0
        phases/phase1_single_llm/reporting/llm_logger      ← Phase 1  (tokens / prompt / response)
        phases/phase2_critique/reporting/critique_logger   ← Phase 2  (cost + critic behaviour)
                         │
                         ▼
                    results/<tool>_<timestamp>.json  +  .csv
```

---

## 5. How to run (from the project root)

Everything runs as a module with `python3 -m` so imports resolve:

```bash
# Phase 0
python3 -m phases.phase0_traditional.run --tool slither
python3 -m phases.phase0_traditional.run --tool mythril            # requires Docker

# Phase 1  (needs GITHUB_TOKEN in .env)
python3 -m phases.phase1_single_llm.run --model gpt4o

# Phase 2  (needs GITHUB_TOKEN in .env)
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt4o

# Re-analyse a saved Phase 2 run (no API calls)
python3 -m phases.phase2_critique.reporting.critique_compare

# Phase 3  (needs GITHUB_TOKEN in .env)
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini

# Analyse a saved Phase 3 run (no API calls)
python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour --run-name <name>

# Phase 4  (needs GITHUB_TOKEN + a cached Phase 0 slither run)
python3 -m phases.phase4_hybrid.run --model gpt4o-mini

# Analyse a saved Phase 4 run (no API calls)
python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name <name> --model gpt4o-mini

# Add --dry-run to any phase for the first 3 contracts only
```

---

## 6. Naming conventions

### Result files
Written to `results/` as a matched JSON + CSV pair sharing one UTC timestamp:

```
<tool>_<timestamp>.json   /   <tool>_<timestamp>.csv
```

- **Phase 0** `<tool>` = tool name — `slither_20260606T154745Z.json`
- **Phase 1** `<tool>` = `<model>_<strategy>` — `gpt41-nano_chain_of_thought_20260619T145544Z.json`
- **Phase 2** `<tool>` = `critique_<detector>_to_<critic>_<strategy>` —
  `critique_gpt4o-mini_to_gpt4o_chain_of_thought_20260619T154837Z.json`
- **Phase 2 analysis** adds `_comparison.{md,csv}` (from `critique_compare.py`).
- **Phase 3** writes into a per-run-name subfolder
  `results/phase3_multi_agent/<run-name>/` with `<tool>_run<N>_<timestamp>.json`
  (one pair per variance run, `<tool>` = e.g. `multiagent_gpt4o-mini`,
  `multiagent_gpt4o-mini_union`, `multiagent_gpt4o-mini_2spec`) plus a single
  `variance.json` (mean ± std F1 across runs).
- **Phase 4** writes into a per-run-name subfolder
  `results/phase4_hybrid/<run-name>/` with `<tool>_run<N>_<timestamp>.json`
  (`<tool>` = `hybrid_slither_<model>`, e.g. `hybrid_slither_gpt4o-mini`) plus a
  single `variance.json`. Each JSON also records `skip_rate`, `confirmed_total`,
  `rejected_total`, and per-contract Slither input + confirm/reject decisions.

Timestamp format: `YYYYMMDDTHHMMSSZ` (UTC).

### Model keys  *(short key → GitHub Models ID, in `shared/config/models.py`)*
`gpt4o-mini` · `gpt4o` · `gpt41` · `gpt41-nano` · `gpt5` · `gpt5-mini` · `deepseek-r1`

### Prompting strategies
`zero_shot` · `few_shot` · `chain_of_thought`  (the critic uses the separate `critique` prompt)

### Canonical vulnerability classes  *(defined once in `shared/core/schema.py`)*
`reentrancy` · `access_control` · `timestamp_dependency`

### Import style
Fully-qualified from the project root — `shared.core.*`, `shared.datasets.*`,
`phases.phaseN_*.…`. Run with `python3 -m` from the root so they resolve.

---

## 7. Quick "where do I…?" index

| I want to… | Go to |
|---|---|
| Run a phase | `python3 -m phases.<phase>.run` (see §5) |
| Add a new detector to a phase | new file in that phase's `tools/`, register it in that phase's `run.py` |
| Add a prompting strategy | new file in `phases/phase1_single_llm/prompts/`, add to `_STRATEGY_MODULES` in `llm_single_agent.py` |
| Add a model | add key → ID in `MODEL_CATALOG` (`shared/config/models.py`) |
| Change what a metric means | `shared/core/scorer.py` + `docs/METRICS_GLOSSARY.md` |
| Change vulnerability classes in scope | `shared/core/schema.py` + `shared/datasets/smartbugs_loader.py` |
| Add a dataset | new loader in `shared/datasets/` returning `GroundTruth[]` |
| Change output columns | `shared/core/logger.py` (base) or the phase logger in that phase's `reporting/` |
| Re-analyse a Phase 2 run | `python3 -m phases.phase2_critique.reporting.critique_compare` |
| Analyse a Phase 3 run | `python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour --run-name <name>` |
| Analyse a Phase 4 run | `python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name <name> --model <model>` |
| Change a phase's model | edit `shared/config/models.py` (`PHASE1_MODEL`, `PHASE2_*`, `PHASE3_MODEL`, `PHASE4_MODEL`) |
| Set up the environment / token | `docs/SETUP.md` |
