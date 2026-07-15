# Phase 4 — Hybrid (LLM filters Slither)

Take Slither's findings from Phase 0 and have an LLM confirm or reject each one.
Question: does a cheap LLM + Slither beat a strong LLM on its own, for less cost?

## What this phase does (plain terms)

- Reads Slither's cached findings from Phase 0 (Slither is **not** re-run).
- Keeps only the in-scope findings for our 3 classes.
- Asks one LLM to mark each finding **confirmed** or **rejected**; only confirmed
  ones are kept. The LLM cannot add new findings.
- If Slither found nothing for a contract, the LLM call is **skipped** (saves cost).
- Runs the dataset **3 times** (default) for mean ± std F1.

## Run it

Needs a cached Phase 0 Slither result first:
`python3 -m phases.phase0_traditional.run --tool slither`.
Choose the provider in `shared/config/models.py` with `USE_OPENAI`, and put the
matching key in `.env`.

**Step 1 — run the hybrid:**

```bash
# GitHub Models — FREE   (USE_OPENAI = False, needs GITHUB_TOKEN)
python3 -m phases.phase4_hybrid.run --model gpt-4o-mini

# OpenAI — PAID          (USE_OPENAI = True, needs OPENAI_API_KEY)
python3 -m phases.phase4_hybrid.run --model gpt-4.1-nano
```

**Step 2 — analyse the saved run** (Slither vs LLM vs hybrid, skip rate,
false-positive reduction; no API calls). Match `--run-name`/`--model` to Step 1:

```bash
# GitHub
python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name hybrid_slither_gpt-4o-mini --model gpt-4o-mini

# OpenAI
python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name hybrid_slither_gpt-4.1-nano --model gpt-4.1-nano
```

Available models — GitHub: `gpt-4o-mini`, `gpt-4o`; OpenAI: `gpt-4.1-nano`,
`gpt-5.5`, `o3`. Add `--dry-run` for the first 3 contracts only.

Results: `results/phase4_hybrid/<run-name>/`. Full details: `docs/PHASE4.md`.
