# core/ — Shared evaluation harness

The phase-agnostic engine that every phase builds on. Nothing here knows about
LLMs, Slither, or Mythril specifically — it only knows the `Prediction` /
`GroundTruth` data shapes and how to score and log them.

## Files

| File | Purpose |
|---|---|
| `schema.py` | Core dataclasses: `Vulnerability`, `GroundTruth`, `Prediction`, and the canonical `VULNERABILITY_CLASSES` list. Everything downstream depends on this — keep it small and stable. |
| `runner.py` | `run_evaluation(ground_truths, tool_fn)` — runs a tool over every contract, normalises contract IDs, catches tool crashes, and hands `(GroundTruth, Prediction)` pairs to the scorer. The single place the plug-in contract is enforced. |
| `scorer.py` | `score(pairs)` — computes per-class TP/FP/FN, precision, recall, F1, plus micro- and macro-averages. Returns a `ScorerReport`. |
| `logger.py` | `log(report)` — writes the base JSON + CSV result files into `results/`. The LLM phases extend this in `reporting/`. |

## The plug-in contract

Any detector is just a function `run(contract_path: str) -> Prediction`. That
is the only thing `runner.py` requires, which is why traditional tools, single
LLMs, and multi-agent pipelines all share this harness unchanged.

## Run the built-in smoke tests (no network needed)

```bash
python3 core/scorer.py     # synthetic pairs, asserts known P/R/F1
python3 core/logger.py     # writes to a temp dir, asserts JSON + CSV shape
python3 core/runner.py     # perfect-mock tool over the dataset, asserts 1.0 everywhere
```

> Formerly named `pipeline/`. Renamed to `core/` during the Phase 2 restructure;
> behaviour is unchanged.
