# tests/ — Standalone checks

Lightweight, dependency-free checks. No test framework required — each file is
runnable with plain `python3` and exits non-zero on failure.

## Files

| File | What it checks |
|---|---|
| `test_loader.py` | The SmartBugs loader: returns 54 contracts with the expected per-class counts (31 / 18 / 5), all classes in scope, all paths exist on disk, IDs unique, one label per contract. |

## Run

```bash
python3 tests/test_loader.py
```

> The core harness modules (`core/scorer.py`, `core/logger.py`,
> `core/runner.py`) also carry their own `__main__` smoke tests — run them
> directly to verify scoring/logging/running wiring without any network calls.
