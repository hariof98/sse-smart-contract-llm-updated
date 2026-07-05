# Phase 1 — Single-LLM Detection

**Question (RQ3 + prompting side of RQ1):** How well does a single LLM detect
vulnerabilities, and how much does the prompting strategy matter? Also provides
the single-agent baseline that Phase 2 is compared against.

## What it does

Sends each SmartBugs Curated contract to one LLM (via the GitHub Models API),
asks for a `{"vulnerabilities": [...]}` answer, parses it, and scores it with
the same harness Phase 0 uses. Records token usage, cost estimate, the full
prompt, and the model response for every contract.

## Contents

| File | What it does |
|---|---|
| `run.py` | Entry point: one model, fixed `chain_of_thought` strategy, over all contracts. |
| `tools/llm_single_agent.py` | The LLM detector **and** the shared LLM plumbing (`call_chat`, `parse_vulnerabilities`, `SUPPORTED_MODELS`) reused by Phase 2. |
| `prompts/zero_shot.py` | Contract only, no examples. |
| `prompts/few_shot.py` | Three worked examples (one per class), then the contract. |
| `prompts/chain_of_thought.py` | Step-by-step reasoning, then a final JSON answer. Default — best F1, and produces the reasoning Phase 2's critic needs. |
| `reporting/llm_logger.py` | Writes results enriched with tokens / prompt / response. |

## Command reference

Run from the **project root** (needs `GITHUB_TOKEN` in `.env` — see `docs/SETUP.md`).

**Master command** (runs the full phase):

```bash
python3 -m phases.phase1_single_llm.run --model gpt4o-mini
```

Other commands:

```bash
python3 -m phases.phase1_single_llm.run --model gpt4o          # a different model
python3 -m phases.phase1_single_llm.run --model gpt41
python3 -m phases.phase1_single_llm.run --model gpt4o-mini --dry-run   # first 3 contracts, nothing saved
```

Model keys: `gpt4o-mini`, `gpt4o`, `gpt41`, `gpt41-nano`, `gpt5`, `gpt5-mini`,
`deepseek-r1` (from `shared/config/models.py`). Results are written to
`results/phase1_single_llm/<model>_chain_of_thought_<timestamp>.json` and `.csv`.

## Depends on

`shared/core` and `shared/datasets`. See `docs/PHASE1.md` and
`docs/PHASE1_SUMMARY.md`.
