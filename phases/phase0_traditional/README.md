# Phase 0 — Traditional Tools

**Question (RQ3):** How well do traditional static/symbolic tools do on this
task? This is the baseline every later phase is measured against.

## What it does

Runs an established security tool over every in-scope SmartBugs Curated
contract, maps the tool's native findings to our three canonical classes
(`reentrancy`, `access_control`, `timestamp_dependency`), scores them against
ground truth, and saves a JSON + CSV result pair.

## Contents

| File | What it does |
|---|---|
| `run.py` | Entry point: loads the dataset, runs the chosen tool, prints + saves results. |
| `tools/slither_tool.py` | Slither (static analysis) via subprocess; maps detector slugs → canonical classes. |
| `tools/mythril_tool.py` | Mythril (symbolic execution) via Docker; maps SWC IDs → canonical classes. |
| `tools/patch_mythril_docker.sh` | Helper to build the patched Mythril Docker image. |

## Command reference

Run from the **project root**.

**Master command** (runs the full phase):

```bash
python3 -m phases.phase0_traditional.run --tool slither
```

Other commands:

```bash
python3 -m phases.phase0_traditional.run --tool mythril            # requires Docker
python3 -m phases.phase0_traditional.run --tool slither --dry-run  # first 3 contracts, nothing saved
```

Results are written to `results/phase0_traditional/<tool>_<timestamp>.json` and
`.csv`. Mythril needs a patched Docker image first (see
`tools/patch_mythril_docker.sh` and `docs/SETUP.md`).

## Depends on

`shared/core` (runner, scorer, logger, schema) and `shared/datasets`
(SmartBugs loader). See `docs/PHASE0.md` for the full design walkthrough.
