# docs/ — Documentation

| File                  | What it covers                                                                                                       |
| --------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `SETUP.md`            | Environment setup: Python deps, Slither/solc, Docker/Mythril, and the `GITHUB_TOKEN` `.env` file for the LLM phases. |
| `METRICS_GLOSSARY.md` | Definitions of every metric: TP/FP/FN, precision, recall, F1, micro vs macro, and cost-adjusted F1.                  |
| `PHASE0.md`           | Phase 0 — traditional tools (Slither, Mythril). Full internal walkthrough of the harness and how it was built.       |
| `PHASE1.md`           | Phase 1 — single-LLM detection and prompting strategies.                                                             |
| `PHASE1_SUMMARY.md`   | Phase 1 results summary and preliminary findings.                                                                    |
| `PHASE2.md`           | Phase 2 — two-agent detector → critic pipeline: design, experimental matrix, what to measure, and how to run it.     |
| `PHASE3.md`           | Phase 3 — multi-agent specialists + moderator: design, experimental matrix, per-specialist recall, moderator behaviour, and how to run it. |

> Note: `PHASE0.md` and `PHASE1.md` were previously `README_INTERNAL.md` and
> `README_PHASE1.md` at the project root. They were moved here during the
> Phase 2 restructure; their contents are unchanged.
