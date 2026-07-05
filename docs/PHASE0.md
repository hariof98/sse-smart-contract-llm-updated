# Phase 0 — Internal Development Log

**Project:** MSc Practicum — Evaluating LLMs for Smart Contract Vulnerability Detection  
**Phase:** 0 — Evaluation pipeline construction and traditional-tool baseline  
**Status:** Pipeline complete. Slither installed and working. Mythril ready (requires Docker).

---

## Table of Contents

1. [Project Goal](#1-project-goal)
2. [Directory Structure](#2-directory-structure)
3. [Core Data Structures](#3-core-data-structures)
4. [Dataset](#4-dataset)
5. [Step-by-Step Build Log](#5-step-by-step-build-log)
   - [Step 1 — Dataset loader](#step-1--dataset-loader)
   - [Step 2 — Slither tool wrapper](#step-2--slither-tool-wrapper)
   - [Step 3 — Scorer](#step-3--scorer)
   - [Step 4 — Runner](#step-4--runner)
   - [Step 5 — Logger](#step-5--logger)
   - [Step 6 — Top-level script](#step-6--top-level-script)
   - [Step 7 — Mythril tool wrapper](#step-7--mythril-tool-wrapper)
6. [How to Run Everything](#6-how-to-run-everything)
7. [How to Add a New Tool](#7-how-to-add-a-new-tool)
8. [Known Issues and Design Decisions](#8-known-issues-and-design-decisions)
9. [What Comes Next (Phase 1)](#9-what-comes-next-phase-1)

---

## 1. Project Goal

Build a **pluggable evaluation harness** that can run any vulnerability-detection tool
(static analyser, symbolic executor, or LLM) over a labelled Solidity dataset and
produce standardised precision / recall / F1 scores.

Phase 0 scope:
- **Dataset:** SmartBugs Curated (cloned into `datasets/smartbugs-curated/`)
- **Vulnerability classes:** `reentrancy`, `access_control`, `timestamp_dependency`
- **Tools:** Slither (static analysis) and Mythril (symbolic execution)
- **Matching criterion:** class-only — a prediction is a TP if tool and ground truth name the same class for the same contract

---

## 2. Directory Structure

```
practicum/
├── configs/                          # (empty — reserved for future config files)
├── datasets/
│   ├── __init__.py
│   ├── smartbugs_loader.py           # ← Step 1
│   └── smartbugs-curated/dataset/    # cloned SmartBugs dataset
│       ├── access_control/           # 18 .sol files
│       ├── arithmetic/               # skipped (not in scope)
│       ├── bad_randomness/           # skipped
│       ├── denial_of_service/        # skipped
│       ├── front_running/            # skipped
│       ├── reentrancy/               # 31 .sol files
│       ├── short_addresses/          # skipped
│       ├── time_manipulation/        # 5 .sol files → timestamp_dependency
│       └── unchecked_low_level_calls/ # skipped
├── pipeline/
│   ├── __init__.py
│   ├── schema.py                     # core data structures (pre-existing)
│   ├── scorer.py                     # ← Step 3
│   ├── runner.py                     # ← Step 4
│   └── logger.py                     # ← Step 5
├── results/                          # output JSON + CSV files written here
├── tools/
│   ├── __init__.py
│   ├── slither_tool.py               # ← Step 2
│   └── mythril_tool.py               # ← Step 7
├── test_loader.py                    # ← Step 1 test
├── run_phase0.py                     # ← Step 6 (top-level entry point)
├── demo_schema.py                    # pre-existing demo
├── README.md                         # project-level readme
├── README_INTERNAL.md                # this file
└── SETUP.md
```

---

## 3. Core Data Structures

Defined in `pipeline/schema.py`. **All tools and all datasets use these — do not change them.**

```python
VULNERABILITY_CLASSES = ["reentrancy", "access_control", "timestamp_dependency"]

@dataclass
class Vulnerability:
    vuln_class: str          # must be one of VULNERABILITY_CLASSES
    function: Optional[str]  # function name if known (optional)
    line: Optional[int]      # line number if known (optional)

@dataclass
class GroundTruth:
    contract_id: str         # unique key, e.g. "reentrancy/simple_dao.sol"
    contract_path: str       # absolute path to the .sol file
    vulnerabilities: list[Vulnerability]

@dataclass
class Prediction:
    contract_id: str
    tool_name: str           # "slither", "mythril", "gpt-4o", …
    vulnerabilities: list[Vulnerability]
    runtime_seconds: float
    tokens_used: Optional[int]   # LLMs only
    raw_output: Optional[str]    # full tool output, for debugging
```

---

## 4. Dataset

**SmartBugs Curated** — 140 labelled Solidity contracts across 9 vulnerability folders.

Only 3 folders are in scope for Phase 0:

| Folder | Canonical class | Contracts |
|---|---|---|
| `reentrancy/` | `reentrancy` | 31 |
| `access_control/` | `access_control` | 18 |
| `time_manipulation/` | `timestamp_dependency` | 5 |
| *(6 other folders)* | *(skipped)* | — |
| **Total in scope** | | **54** |

Ground truth is folder-based: every `.sol` file inside a folder is labelled with that folder's vulnerability class.

**Solidity compiler versions used by these contracts:**

| Version | Count |
|---|---|
| `^0.4.x` (various) | 52 |
| `^0.5.0` | 1 |
| `^0.8.x` | 1 |

This matters for Slither — see Step 2.

---

## 5. Step-by-Step Build Log

---

### Step 1 — Dataset loader

**File created:** `datasets/smartbugs_loader.py`  
**Test file:** `test_loader.py`

#### What it does

`load_smartbugs(dataset_root=None) → list[GroundTruth]`

- Walks `datasets/smartbugs-curated/dataset/`
- Maps folder names to canonical classes via `FOLDER_TO_CLASS`
- Skips all folders not in the mapping
- Returns a sorted list of 54 `GroundTruth` objects

#### Folder → class mapping

```python
FOLDER_TO_CLASS = {
    "reentrancy":        "reentrancy",
    "access_control":    "access_control",
    "time_manipulation": "timestamp_dependency",
}
```

#### How to run

```bash
cd ~/Desktop/practicum
python3 test_loader.py
```

#### Expected output

```
[PASS] returns 54 GroundTruth objects
[PASS] all vulnerability classes are in VULNERABILITY_CLASSES
[PASS] reentrancy: 31 contracts
[PASS] access_control: 18 contracts
[PASS] timestamp_dependency: 5 contracts
[PASS] total: 54 contracts
[PASS] all 54 contract paths exist on disk
[PASS] all 54 contract_ids are unique
[PASS] each contract has exactly one vulnerability label

All 6/6 tests passed.
```

---

### Step 2 — Slither tool wrapper

**File created:** `tools/slither_tool.py`

#### What it does

`run(contract_path: str) → Prediction`

1. Reads the contract's `pragma solidity` line to determine the required compiler version
2. Looks up the matching `solc` binary installed by `solc-select`
3. Runs `slither <contract> --json - --disable-color --solc <binary>`
4. Parses the JSON output and maps detector names to canonical classes
5. Returns a `Prediction` — always, never raises

#### Detector → canonical class mapping

| Slither detector | Canonical class |
|---|---|
| `reentrancy-eth` | `reentrancy` |
| `reentrancy-no-eth` | `reentrancy` |
| `reentrancy-benign` | `reentrancy` |
| `reentrancy-events` | `reentrancy` |
| `reentrancy-unlimited-gas` | `reentrancy` |
| `suicidal` | `access_control` |
| `unprotected-upgrade` | `access_control` |
| `controlled-delegatecall` | `access_control` |
| `tx-origin` | `access_control` |
| `timestamp` | `timestamp_dependency` |

All other detectors are silently ignored.

#### Installation (one-time)

```bash
# Install Slither
python3 -m pip install slither-analyzer

# Install solc version manager
python3 -m pip install solc-select

# Install the solc versions needed for SmartBugs contracts
~/Library/Python/3.12/bin/solc-select install 0.4.25
~/Library/Python/3.12/bin/solc-select install 0.5.17
~/Library/Python/3.12/bin/solc-select install 0.8.20
~/Library/Python/3.12/bin/solc-select use 0.8.20

# (Optional) add to PATH permanently so you can type 'slither' directly
echo 'export PATH="$HOME/Library/Python/3.12/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

#### How to run (smoke-test)

```bash
python3 tools/slither_tool.py
# or test a specific contract:
python3 tools/slither_tool.py datasets/smartbugs-curated/dataset/reentrancy/reentrancy_simple.sol
```

#### Expected output

```
Running Slither on: .../reentrancy/0x01f8c4e3fa3edeb29e514cba738d87ce8c091d3f.sol
  tool        : slither
  contract_id : 0x01f8c4e3fa3edeb29e514cba738d87ce8c091d3f.sol
  runtime     : 4.09s
  findings    : 1
    - reentrancy  fn=Collect  line=47
```

#### Debugging notes encountered during development

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pipeline'` | Running `python3 tools/slither_tool.py` puts `tools/` on `sys.path` instead of the project root | Added `sys.path.insert(0, project_root)` at top of file |
| `No JSON output. stderr:` (0.3s runtime) | `slither` binary not on subprocess PATH, so `solc` not found, Slither exits silently | Inject `~/Library/Python/3.12/bin` into subprocess `env["PATH"]` |
| `No JSON output.` (1.8s runtime) | `solc 0.8.20` incompatible with `pragma solidity ^0.4.19` — Slither crashed with unhandled exception, no stdout/stderr produced | Parse pragma from contract, pass `--solc ~/.solc-select/artifacts/solc-0.4.25/solc-0.4.25` |

---

### Step 3 — Scorer

**File created:** `pipeline/scorer.py`

#### What it does

`score(pairs: list[tuple[GroundTruth, Prediction]]) → ScorerReport`

For each contract and each of the 3 vulnerability classes, classifies the result as:

| Condition | Counter |
|---|---|
| GT has class C **and** tool predicted C | TP |
| GT lacks class C **and** tool predicted C | FP |
| GT has class C **and** tool missed C | FN |

Then computes:
- **Per-class:** precision = TP / (TP+FP), recall = TP / (TP+FN), F1 = harmonic mean
- **Micro-average:** sum all TP/FP/FN first, then compute rates
- **Macro-average:** compute per-class scores first, then mean (only over classes present in GT)
- **Runtime:** total and mean per contract

#### Key classes

```
ClassMetrics    — tp/fp/fn + precision/recall/f1 for one class
OverallMetrics  — micro and macro averages
ScorerReport    — wraps everything; .summary_table() returns the printed table
```

#### How to run (smoke-test)

```bash
python3 pipeline/scorer.py
```

#### Expected output

```
Tool: mock  |  contracts: 6
Runtime: total=6.0s  mean=1.00s

Class                          Precision    Recall        F1  Counts
------------------------------------------------------------------------
reentrancy                         0.333     0.500     0.400  TP=1 FP=2 FN=1
access_control                     1.000     0.500     0.667  TP=1 FP=0 FN=1
timestamp_dependency               1.000     1.000     1.000  TP=1 FP=0 FN=0
------------------------------------------------------------------------
micro-avg                          0.600     0.600     0.600
macro-avg                          0.778     0.667     0.689

All assertions passed.
```

---

### Step 4 — Runner

**File created:** `pipeline/runner.py`

#### What it does

`run_evaluation(ground_truths, tool_fn, verbose=True, progress=True) → ScorerReport`

1. Loops over every `GroundTruth` in order
2. Calls `tool_fn(gt.contract_path)` to get a `Prediction`
3. If the tool raises unexpectedly, wraps the traceback in an empty `Prediction` (pipeline never crashes)
4. Normalises `contract_id` on the prediction to match ground truth
5. Prints a live progress line per contract
6. Calls `score()` and returns the `ScorerReport`

#### The plug-in contract

Any tool only needs to implement **one function:**

```python
def run(contract_path: str) -> Prediction:
    ...
```

#### How to run (smoke-test with perfect mock tool)

```bash
python3 pipeline/runner.py
```

#### Expected output (truncated)

```
=== Runner smoke-test (perfect mock tool) ===

[  1/54] access_control/FibonacciBalance.sol ... 0.0s  findings=1 (access_control)
[  2/54] access_control/arbitrary_location_write_simple.sol ... 0.0s  findings=1 (access_control)
...
[ 54/54] time_manipulation/timed_crowdsale.sol ... 0.0s  findings=1 (timestamp_dependency)

Tool: perfect_mock  |  contracts: 54
...
micro-avg    1.000     1.000     1.000

All assertions passed — runner wiring is correct.
```

---

### Step 5 — Logger

**File created:** `pipeline/logger.py`

#### What it does

`log(report, results_dir=None) → LogPaths`

Writes two files per run — both share the same UTC timestamp in their filename:

**`results/slither_20260516T174500Z.json`** — full detail:
```json
{
  "tool": "slither",
  "num_contracts": 54,
  "total_runtime_seconds": 210.4,
  "mean_runtime_seconds": 3.9,
  "per_class": {
    "reentrancy": {"tp": 24, "fp": 1, "fn": 7, "precision": 0.96, "recall": 0.77, "f1": 0.86}
  },
  "overall": {
    "micro": {"tp": ..., "precision": ..., "recall": ..., "f1": ...},
    "macro": {"precision": ..., "recall": ..., "f1": ...}
  },
  "contracts": [
    {"contract_id": "reentrancy/simple_dao.sol", "gt_classes": ["reentrancy"],
     "pred_classes": ["reentrancy"], "tp": ["reentrancy"], "fp": [], "fn": [],
     "runtime_seconds": 3.8}
  ]
}
```

**`results/slither_20260516T174500Z.csv`** — one row per contract:

| contract_id | gt_classes | pred_classes | tp_classes | fp_classes | fn_classes | runtime_seconds | gt_reentrancy | pred_reentrancy | … |
|---|---|---|---|---|---|---|---|---|---|
| reentrancy/simple_dao.sol | reentrancy | reentrancy | reentrancy | | | 3.8 | 1 | 1 | … |

The binary `gt_<class>` / `pred_<class>` columns make it easy to load into pandas or Excel.

#### How to run (smoke-test)

```bash
python3 pipeline/logger.py
```

#### Expected output

```
[PASS] JSON written to mock_TEST.json
       keys: ['tool', 'num_contracts', 'total_runtime_seconds', 'mean_runtime_seconds', 'per_class', 'overall', 'contracts']
[PASS] CSV written to mock_TEST.csv
       columns: ['contract_id', 'gt_classes', 'pred_classes', 'tp_classes', 'fp_classes', 'fn_classes', 'runtime_seconds', 'gt_reentrancy', 'pred_reentrancy', 'gt_access_control', 'pred_access_control', 'gt_timestamp_dependency', 'pred_timestamp_dependency']

All assertions passed.
```

---

### Step 6 — Top-level script

**File created:** `run_phase0.py`

#### What it does

Wires together all five components (loader → runner → scorer → logger) and prints a summary table.

#### Usage

```bash
# Full run — all 54 contracts (5–15 minutes for Slither)
python3 run_phase0.py

# Quick sanity check — first 3 contracts only, no files saved
python3 run_phase0.py --dry-run

# Run with Mythril instead (requires Docker — see Step 7)
python3 run_phase0.py --tool mythril

# Override dataset path
python3 run_phase0.py --dataset /path/to/other/dataset/
```

#### Dry-run output (confirmed working)

```
[dry-run] limiting to 3 contracts

Dataset : SmartBugs Curated  (3 contracts)
Tool    : slither
Classes : reentrancy, access_control, timestamp_dependency

[  1/3] access_control/FibonacciBalance.sol ... 0.9s  findings=1 (access_control)
[  2/3] access_control/arbitrary_location_write_simple.sol ... 0.7s  findings=0 (—)
[  3/3] access_control/incorrect_constructor_name1.sol ... 0.7s  findings=0 (—)

========================================================================
Tool: slither  |  contracts: 3
Runtime: total=2.3s  mean=0.78s

Class                          Precision    Recall        F1  Counts
------------------------------------------------------------------------
reentrancy                         0.000     0.000     0.000  TP=0 FP=0 FN=0
access_control                     1.000     0.333     0.500  TP=1 FP=0 FN=2
timestamp_dependency               0.000     0.000     0.000  TP=0 FP=0 FN=0
------------------------------------------------------------------------
micro-avg                          1.000     0.333     0.500
macro-avg                          1.000     0.333     0.500
========================================================================
Wall time: 2.3s

[dry-run] results not saved to disk.
```

The dry-run already reveals an expected pattern: Slither detected `access_control` in
`FibonacciBalance.sol` (TP) but missed `arbitrary_location_write_simple.sol` and
`incorrect_constructor_name1.sol` — those use vulnerability patterns not in our
detector map (`arbitrary-location-write`, constructor naming issue). This is legitimate
and interesting data for the evaluation.

---

### Step 7 — Mythril tool wrapper

**File created:** `tools/mythril_tool.py`

#### What it does

`run(contract_path: str) → Prediction`

1. Resolves the absolute contract path
2. Mounts the contract's parent directory as `/mnt` inside a Docker container
3. Runs `docker run --rm -v <dir>:/mnt mythril/myth analyze /mnt/<file> -o json --execution-timeout 60`
4. Parses the JSON issues and maps SWC IDs to canonical classes
5. Returns a `Prediction` — always, never raises

#### SWC ID → canonical class mapping

| SWC ID | Title | Canonical class |
|---|---|---|
| SWC-107 | Reentrancy | `reentrancy` |
| SWC-105 | Unprotected Ether Withdrawal | `access_control` |
| SWC-106 | Unprotected SELFDESTRUCT | `access_control` |
| SWC-112 | Delegatecall to Untrusted Callee | `access_control` |
| SWC-115 | Authorization through tx.origin | `access_control` |
| SWC-116 | Block values / Timestamp Dependence | `timestamp_dependency` |

#### Timeouts

| Parameter | Value | Reason |
|---|---|---|
| `EXECUTION_TIMEOUT` | 60s | Symbolic execution budget per contract |
| `SUBPROCESS_TIMEOUT` | 120s | Hard kill — covers execution + Docker startup |
| `--solver-timeout` | 10000ms | Z3 solver budget |

Mythril is much slower than Slither. A full 54-contract run takes approximately
**2–3 hours** with these settings. Use `--dry-run` first.

#### Installation (one-time)

```bash
# 1. Install Docker Desktop
#    https://www.docker.com/products/docker-desktop/
#    (Start Docker Desktop and ensure it is running before continuing)

# 2. Pull the Mythril image (~1 GB, one-time download)
docker pull mythril/myth

# 3. Verify
docker run --rm mythril/myth version
```

#### How to run (smoke-test)

```bash
python3 tools/mythril_tool.py
# or test a specific contract:
python3 tools/mythril_tool.py datasets/smartbugs-curated/dataset/reentrancy/reentrancy_simple.sol
```

#### Expected output (Docker installed)

```
Running Mythril on: .../reentrancy/reentrancy_simple.sol
  execution-timeout : 60s
  subprocess-timeout: 120s

  tool        : mythril
  contract_id : reentrancy_simple.sol
  runtime     : 45.2s
  findings    : 1
    - reentrancy  line=20
```

#### Expected output (Docker not yet installed)

```
  findings    : 0
  raw_output  : docker executable not found.
Install Docker Desktop and pull the image with:
  docker pull mythril/myth
```

---

## 6. How to Run Everything

### Prerequisites checklist

```bash
# Python 3.10+ required
python3 --version

# Install Slither and solc tools
python3 -m pip install slither-analyzer solc-select

# Install solc versions for SmartBugs contracts
~/Library/Python/3.12/bin/solc-select install 0.4.25
~/Library/Python/3.12/bin/solc-select install 0.5.17
~/Library/Python/3.12/bin/solc-select install 0.8.20

# For Mythril only: install Docker Desktop, then:
docker pull mythril/myth
```

### Running each component individually

```bash
cd ~/Desktop/practicum

# 1. Verify dataset loader
python3 test_loader.py

# 2. Smoke-test Slither wrapper (one contract)
python3 tools/slither_tool.py

# 3. Smoke-test scorer (synthetic data, no tool needed)
python3 pipeline/scorer.py

# 4. Smoke-test runner (mock tool, no Slither needed)
python3 pipeline/runner.py

# 5. Smoke-test logger (synthetic data, writes to /tmp)
python3 pipeline/logger.py

# 6. Smoke-test Mythril wrapper (one contract)
python3 tools/mythril_tool.py
```

### Running the full evaluation

```bash
cd ~/Desktop/practicum

# Sanity check (3 contracts, ~5s, no files saved)
python3 run_phase0.py --dry-run

# Full Slither run (54 contracts, ~5–15 minutes)
python3 run_phase0.py

# Full Mythril run (54 contracts, ~2–3 hours — requires Docker)
python3 run_phase0.py --tool mythril
```

Results are saved to `results/` as:
- `results/slither_<timestamp>.json`
- `results/slither_<timestamp>.csv`

---

## 7. How to Add a New Tool

To add GPT-4, Claude, or any other tool:

1. Create `tools/<toolname>_tool.py`
2. Implement exactly one function:

```python
def run(contract_path: str) -> Prediction:
    # analyse the contract
    # map findings to canonical VULNERABILITY_CLASSES
    # return Prediction — never raise
    return Prediction(
        contract_id=Path(contract_path).name,
        tool_name="my_tool",
        vulnerabilities=[...],
        runtime_seconds=elapsed,
        tokens_used=n,          # for LLMs
        raw_output=raw,
    )
```

3. Register it in `run_phase0.py`:

```python
def _get_tool(name: str):
    if name == "my_tool":
        from tools.my_tool import run
        return run
```

4. Run it: `python3 run_phase0.py --tool my_tool`

No other code changes required.

---

## 8. Known Issues and Design Decisions

### Solc version detection

Slither requires the exact solc version matching the contract's `pragma solidity` directive.
The wrapper parses the pragma and looks up the binary from solc-select's artifact directory
(`~/.solc-select/artifacts/solc-{version}/solc-{version}`). If no matching version is
installed, it falls back to whatever `solc` is on PATH.

**Currently installed:** 0.4.25, 0.5.17, 0.8.20  
**SmartBugs Curated needs:** mostly 0.4.x (52/54 contracts), one 0.5.0, one 0.8.x

### Slither detector coverage for `access_control`

The SmartBugs `access_control` folder contains diverse patterns: arbitrary write,
incorrect constructors, missing access modifiers, self-destruct without protection.
Our detector map currently covers: `suicidal`, `unprotected-upgrade`,
`controlled-delegatecall`, `tx-origin`. Contracts using other patterns (e.g.
`arbitrary-location-write`, constructor naming bugs) will be false negatives.
This is expected and is precisely what the Phase 0 evaluation will quantify.

### Deduplication per contract

Both Slither and Mythril may fire multiple findings for the same vulnerability class
(e.g. several reentrancy-eth hits in one contract). The wrappers deduplicate to at most
one `Vulnerability` per canonical class per contract, matching the class-only scoring
criterion.

### PATH on macOS without a venv

`pip install` without an active virtual environment installs scripts to
`~/Library/Python/3.12/bin/` which is not on the default PATH. The Slither wrapper
handles this by injecting the directory into the subprocess environment at runtime.

---

## 9. What Comes Next (Phase 1)

- Add SolidiFI dataset (synthetic ground truth with known injected bugs)
- Implement LLM tool wrappers: GPT-4o, Claude 3.5 — same `run()` interface
- Add `tokens_used` tracking to the logger CSV
- Compare baseline (Slither, Mythril) vs. LLM scores per class
- Investigate multi-agent / chain-of-thought prompting strategies
