# Phase 2 — Detector → Critic (two agents)

A first LLM finds vulnerabilities, then a second (different) LLM reviews and
corrects that list. Question: is the extra critic worth its cost?

## What this phase does (plain terms)

- **Detector** LLM reads each contract and lists vulnerabilities (with reasoning).
- **Critic** LLM (a different model) sees the contract + the detector's list and
  reasoning, then returns a corrected list.
- The critic's revised list is what gets scored.
- Both LLMs run on every contract (so ~2 calls per contract).

## Run it

The detector and critic must be **different** models. Choose the provider in
`shared/config/models.py` with `USE_OPENAI`, and put the matching key in `.env`.

```bash
# GitHub Models — FREE   (USE_OPENAI = False, needs GITHUB_TOKEN)
python3 -m phases.phase2_critique.run --detector gpt-4o-mini --critic gpt-4o

# OpenAI — PAID          (USE_OPENAI = True, needs OPENAI_API_KEY)
python3 -m phases.phase2_critique.run --detector gpt-4.1-nano --critic o3
```

Available models — GitHub: `gpt-4o-mini`, `gpt-4o`; OpenAI: `gpt-4.1-nano`,
`gpt-5.5`, `o3`. Add `--dry-run` for the first 3 contracts only.

Results: `results/phase2_critique/`. Full details: `docs/PHASE2.md`.
