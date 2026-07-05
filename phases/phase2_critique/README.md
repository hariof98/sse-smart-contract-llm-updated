# Phase 2 — Two-Agent Detector → Critic

**Question (RQ4):** Does adding a second "critic" LLM justify its extra cost?
The headline metric is not raw F1 but **cost-adjusted F1** (F1 per 1k tokens,
F1 per dollar) versus the Phase 1 single-agent baseline.

## What it does

Runs a cross-model, single-round pipeline:

```
contract → Detector LLM → (classes + reasoning) → Critic LLM → final classes
```

The critic (a different model) sees the contract, the detector's reported
classes, and the detector's reasoning, then returns a revised list — that
revised list is what gets scored. To the harness this is still one tool with
one `run(contract_path) -> Prediction`, so the scorer/runner/logger are
unchanged.

## Contents

| File | What it does |
|---|---|
| `run.py` | Entry point: takes `--detector` and `--critic` model keys, prints cost + critic-behaviour breakdown. |
| `tools/llm_critique.py` | The detector → critic pipeline. Reuses Phase 1's `call_chat`, `parse_vulnerabilities`, and detector `run`. |
| `prompts/critique.py` | The critic's review prompt (a fixed experimental variable). |
| `reporting/critique_logger.py` | Writes results with per-step token split + critic behaviour (fp_removed / tp_removed / tp_added / fp_added / agreed). |
| `reporting/critique_compare.py` | Re-scores a saved run as detector-only vs after-critic — no API calls. |

## Command reference

Run from the **project root** (needs `GITHUB_TOKEN` in `.env`).

**Master command** (runs the full phase):

```bash
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt41-nano
```

Other commands:

```bash
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt4o        # cheap → strong (rate-limit prone)
python3 -m phases.phase2_critique.run --detector gpt4o       --critic gpt4o-mini  # strong → cheap
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt41-nano --verbose   # per-contract detector/critic detail
python3 -m phases.phase2_critique.run --detector gpt4o-mini --critic gpt41-nano --dry-run   # 3 contracts, nothing saved

# Re-analyse a saved run (detector vs after-critic), no API calls:
python3 -m phases.phase2_critique.reporting.critique_compare                 # newest critique_*.json
python3 -m phases.phase2_critique.reporting.critique_compare results/<file>.json
```

Detector defaults to the `chain_of_thought` strategy because the critic needs
reasoning to review. Results are written to
`results/phase2_critique/critique_<detector>_to_<critic>_<strategy>_<timestamp>.json`
and `.csv`. Default critic/detector are set in `shared/config/models.py`.

## Depends on

`shared/core`, `shared/datasets`, and Phase 1's `tools/llm_single_agent` +
`reporting/llm_logger` (reused, not duplicated). See `docs/PHASE2.md`.
