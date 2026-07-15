# shared/ — Cross-phase code

Everything used by more than one phase lives here. It is deliberately **not**
under any single `phases/phase-*` folder because all three phases depend on it.
Nothing here changes when you add a new tool — that is the whole point.

## Contents

| Path | What it is |
|---|---|
| `config/models.py` | **Single source of truth for model selection + provider toggle.** The `USE_OPENAI` flag (GitHub Models free tier vs paid OpenAI), the two provider-scoped catalogs (GitHub → `gpt-4o-mini` (default), `gpt-4o`; OpenAI → `gpt-4.1-nano` (default), `gpt-5.5`, `o3`), the provider-aware per-phase choices (`PHASE1_MODEL`, `PHASE2_DETECTOR`, `PHASE2_CRITIC`, `PHASE3_MODEL`, `PHASE4_MODEL`), and the pricing table. Change a phase's model or the provider here — nothing else. |
| `core/schema.py` | Data types: `Vulnerability`, `GroundTruth`, `Prediction`, and the canonical `VULNERABILITY_CLASSES`. Keep small and stable — everything depends on it. |
| `core/runner.py` | Runs a tool over every contract and pairs each `Prediction` with its `GroundTruth`. |
| `core/scorer.py` | Turns pairs into TP/FP/FN → precision / recall / F1 (micro + macro). |
| `core/logger.py` | Base results writer (JSON + CSV). The phase loggers extend this. |
| `datasets/smartbugs_loader.py` | Loads SmartBugs Curated into `GroundTruth[]` (folder name → class). |
| `datasets/smartbugs-curated/` | The bundled dataset (the actual `.sol` files). |

## The one contract that ties the project together

```python
def run(contract_path: str) -> Prediction
```

Any detector in any phase that implements this (directly or via a
`make_tool(...)` factory) plugs into `shared.core.runner.run_evaluation` with
zero changes to this package.

## Import style

All modules are imported fully-qualified from the project root, e.g.:

```python
from shared.core.runner import run_evaluation
from shared.core.schema import Prediction, Vulnerability
from shared.datasets.smartbugs_loader import load_smartbugs
```

Run things with `python3 -m ...` from the project root so these resolve.
