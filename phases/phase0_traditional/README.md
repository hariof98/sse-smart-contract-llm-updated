# Phase 0 — Traditional Tools

The baseline: run an established security tool over the dataset so every later
phase has something to be compared against. (No LLM, no API key.)

## What this phase does (plain terms)

- Runs Slither (or Mythril) on all 54 SmartBugs contracts.
- Translates each tool's raw findings into our 3 classes: `reentrancy`,
  `access_control`, `timestamp_dependency`.
- Scores them against the known answers and saves the results.

## Run it

```bash
# Slither (the main baseline)
python3 -m phases.phase0_traditional.run --tool slither

# Mythril (requires Docker)
python3 -m phases.phase0_traditional.run --tool mythril
```

Add `--dry-run` to try just the first 3 contracts.

Results: `results/phase0_traditional/<tool>_<timestamp>.json` / `.csv`.
Full details: `docs/PHASE0.md`.
