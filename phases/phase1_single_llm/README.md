# Phase 1 — Single LLM

One LLM reads each contract and lists the vulnerabilities it finds.

## What this phase does (plain terms)

- Sends each of the 54 contracts to a single LLM.
- Asks which of the 3 classes are present, with step-by-step reasoning.
- Parses the answer and scores it against the known answers.
- Records tokens, a cost estimate, and the full model response.

## Run it

Choose the provider in `shared/config/models.py` with the `USE_OPENAI` flag, and
put the matching key in `.env`.

```bash
# GitHub Models — FREE   (USE_OPENAI = False, needs GITHUB_TOKEN)
python3 -m phases.phase1_single_llm.run --model gpt-4o-mini

# OpenAI — PAID          (USE_OPENAI = True, needs OPENAI_API_KEY)
python3 -m phases.phase1_single_llm.run --model gpt-4.1-nano
```

Available models — GitHub: `gpt-4o-mini` (default), `gpt-4o`; OpenAI:
`gpt-4.1-nano` (default), `gpt-5.5`, `o3`. Add `--dry-run` for the first 3
contracts only.

Results: `results/phase1_single_llm/`. Full details: `docs/PHASE1.md`.
