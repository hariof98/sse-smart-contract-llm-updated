# Phase 3 — Multi-Agent (specialists + moderator)

Three specialist LLMs (one per class) look at the contract in parallel, then a
moderator LLM combines their findings into the final answer.

## What this phase does (plain terms)

- Runs 3 specialists at the same time — reentrancy, access_control, timestamp —
  each looking only for its own class and not seeing the others' output.
- A **moderator** then reads the contract + all three lists and produces the
  final list (drops false positives, merges duplicates).
- All four agents use the **same** model; only their instructions differ.
- Runs the whole dataset **3 times** (default) because LLMs aren't perfectly
  repeatable, then reports mean ± std F1.

## Run it

Choose the provider in `shared/config/models.py` with `USE_OPENAI`, and put the
matching key in `.env`.

```bash
# GitHub Models — FREE   (USE_OPENAI = False, needs GITHUB_TOKEN)
python3 -m phases.phase3_multi_agent.run --model gpt-4o-mini

# OpenAI — PAID          (USE_OPENAI = True, needs OPENAI_API_KEY)
python3 -m phases.phase3_multi_agent.run --model gpt-4.1-nano
```

Then analyse the saved run (moderator override rate + per-specialist recall; no
API calls). The run name defaults to `multiagent_<model>`, so match it to what
you ran:

```bash
# GitHub run  -> run name: multiagent_gpt-4o-mini
python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour --run-name multiagent_gpt-4o-mini

# OpenAI run  -> run name: multiagent_gpt-4.1-nano
python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour --run-name multiagent_gpt-4.1-nano
```

Available models — GitHub: `gpt-4o-mini` (default), `gpt-4o`; OpenAI:
`gpt-4.1-nano` (default), `gpt-5.5`, `o3`. Add `--dry-run` for the first 3
contracts, or `--runs 1` for a single pass.

Results: `results/phase3_multi_agent/<run-name>/`. Full details: `docs/PHASE3.md`.
