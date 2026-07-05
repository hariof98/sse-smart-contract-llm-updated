# Practicum — Evaluating LLMs for Smart Contract Vulnerability Detection

An evaluation harness that compares **traditional tools** (Slither, Mythril),
**single LLMs** (Phase 1), **two-agent LLM critique pipelines** (Phase 2),
**multi-agent specialist+moderator pipelines** (Phase 3), and **LLM+tool hybrids**
(Phase 4) on the same Solidity vulnerability-detection task, using the same
dataset and the same metrics so results are directly comparable.

## The core idea — one pluggable interface

Every detector, no matter how complex, plugs in by implementing a single
function:

```python
def run(contract_path: str) -> Prediction
```

The shared harness (`shared/core/`) runs that function over every contract, scores
the predictions against ground truth, and logs precision / recall / F1,
runtime, and (for LLMs) tokens and cost. Adding a new tool never requires
touching the scorer, runner, or logger.

## Project layout

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
│   ├── config/                     models.py — single source of truth for model selection
│   ├── core/                       schema, runner, scorer, logger
│   └── datasets/                   smartbugs_loader + the SmartBugs Curated data
│
├── docs/                         # per-phase docs + metrics glossary + setup + PROJECT_STRUCTURE.md
├── tests/                        # standalone checks (dataset loader)
├── examples/                     # small runnable demos
└── results/                      # JSON + CSV output, one pair per run
```

Each phase folder (and `shared/`) has its own `README.md`. For a full map of
the codebase see `docs/PROJECT_STRUCTURE.md`.

## How to run each phase

Run everything from the **project root** with `python3 -m`:

```bash
# Phase 0 — traditional tools
python3 -m phases.phase0_traditional.run --tool slither
python3 -m phases.phase0_traditional.run --tool mythril           # requires Docker

# Phase 1 — single LLM
python3 -m phases.phase1_single_llm.run --model gpt4o-mini

# Phase 2 — detector -> critic (cross-model)
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt4o

# Phase 3 — three specialists + moderator (same model for all four agents)
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini

# Phase 4 — hybrid: LLM filters cached Slither findings (needs a Phase 0 slither run)
python3 -m phases.phase4_hybrid.run --model gpt4o-mini

# Any phase: add --dry-run to process only the first 3 contracts
```

The LLM phases need a `GITHUB_TOKEN` in a `.env` file (see `docs/SETUP.md`).

To change which model a phase uses by default, edit the single config file
`shared/config/models.py` (`PHASE1_MODEL`, `PHASE2_DETECTOR`, `PHASE2_CRITIC`,
`PHASE3_MODEL`, `PHASE4_MODEL`). The `--model` / `--detector` / `--critic` flags
still override it per run.

## The phases

| Phase | Question it answers                                                                    | Entry point                        | Docs             |
| ----- | -------------------------------------------------------------------------------------- | ---------------------------------- | ---------------- |
| **0** | How well do traditional static/symbolic tools do?                                      | `phases/phase0_traditional/run.py` | `docs/PHASE0.md` |
| **1** | How well does a single LLM do, and how does prompting matter?                          | `phases/phase1_single_llm/run.py`  | `docs/PHASE1.md` |
| **2** | Does adding a second "critic" LLM justify its extra cost?                              | `phases/phase2_critique/run.py`    | `docs/PHASE2.md` |
| **3** | Does a role-specialised multi-agent design (specialists + moderator) justify its cost? | `phases/phase3_multi_agent/run.py` | `docs/PHASE3.md` |
| **4** | Is an LLM+tool hybrid (LLM filters Slither) more cost-effective than either alone?      | `phases/phase4_hybrid/run.py`      | `docs/PHASE4.md` |

## Dataset & scope

- **Dataset:** SmartBugs Curated (54 in-scope contracts).
- **Vulnerability classes:** `reentrancy`, `access_control`, `timestamp_dependency`.
- **Matching:** class-only (a prediction matches if it names the right class
  for the contract).

See `docs/METRICS_GLOSSARY.md` for definitions of every metric (TP/FP/FN,
precision, recall, F1, micro vs macro, cost-adjusted F1).

---

## Command reference

Run all commands from the **project root** (`practicum/`). The LLM phases
(1, 2, 3, 4) need `GITHUB_TOKEN` in `.env`. For each phase the **master command**
runs the entire phase properly; the commands under it are optional variations.

> Tip: add `--dry-run` to any phase's command to process only the first 3
> contracts (nothing is saved) — use it to check things work before a full run.

### Phase 0 — Traditional tools

**Master command:**

```bash
python3 -m phases.phase0_traditional.run --tool slither
```

Other commands:

```bash
python3 -m phases.phase0_traditional.run --tool mythril        # requires Docker
python3 -m phases.phase0_traditional.run --tool slither --dry-run
```

### Phase 1 — Single LLM

**Master command:**

```bash
python3 -m phases.phase1_single_llm.run --model gpt4o-mini
```

Other commands:

```bash
python3 -m phases.phase1_single_llm.run --model gpt4o          # a different model
python3 -m phases.phase1_single_llm.run --model gpt41
python3 -m phases.phase1_single_llm.run --model gpt4o-mini --dry-run
```

### Phase 2 — Detector → Critic

**Master command:**

```bash
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt41-nano
```

Other commands:

```bash
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt4o        # cheap → strong
python3 -m phases.phase2_critique.run --detector gpt4o       --critic gpt4o-mini  # strong → cheap
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt41-nano --verbose   # show per-contract detector/critic detail
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt41-nano --dry-run
# Re-analyse a saved run (detector vs after-critic), no API calls:
python3 -m phases.phase2_critique.reporting.critique_compare
```

### Phase 3 — Multi-agent (specialists + moderator)

**Master command:**

```bash
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini
```

Other commands:

```bash
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini --runs 1         # runs ony 1 time instead of 3
python3 -m phases.phase3_multi_agent.run --model gpt4o --token-cap 0            # uncapped
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini --no-moderator      # ablation: union of specialists
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini --specialists reentrancy,access_control
python3 -m phases.phase3_multi_agent.run --config ablation_no_moderator         # a prepared config
python3 -m phases.phase3_multi_agent.run --model gpt4o-mini --dry-run
python3 -m phases.phase3_multi_agent.run_configs                                # list prepared configs
# Analyse a saved run (override rate + per-specialist recall), no API calls:
python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour --run-name multiagent_gpt4o-mini
```

### Phase 4 — Hybrid (LLM filters Slither output)

Needs a cached Phase 0 Slither result first
(`python3 -m phases.phase0_traditional.run --tool slither`).

**Master command:**

```bash
python3 -m phases.phase4_hybrid.run --model gpt4o-mini
```

Other commands:

```bash
python3 -m phases.phase4_hybrid.run --model gpt4o                               # strong-LLM hybrid
python3 -m phases.phase4_hybrid.run --config primary_mini_hybrid                # a prepared config
python3 -m phases.phase4_hybrid.run --model gpt4o-mini --dry-run
python3 -m phases.phase4_hybrid.run --slither-results results/phase0_traditional/slither_<ts>.json
python3 -m phases.phase4_hybrid.run_configs                                     # list prepared configs
# Analyse a saved run (3-way comparison + skip rate + FP reduction), no API calls:
python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name hybrid_slither_gpt4o-mini --model gpt4o-mini
```
