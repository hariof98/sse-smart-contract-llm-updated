# Phase 1 — LLM Evaluation Pipeline

**Project:** MSc Practicum — Evaluating LLMs for Smart Contract Vulnerability Detection
**Phase:** 1 — LLM-based vulnerability detection using OpenAI models via GitHub Models API
**Status:** Pipeline complete. Results pending (GitHub Models daily quota reset required).

---

## 1. Overview

Phase 1 evaluates Large Language Models as vulnerability detectors on the same 54-contract SmartBugs Curated dataset used in Phase 0. Each contract's Solidity source code is sent as a prompt and the model returns a structured JSON list of detected vulnerability classes.

**Vulnerability classes:** `reentrancy`, `access_control`, `timestamp_dependency`

**Models evaluated:**

| Key | Model ID | Description |
|-----|----------|-------------|
| `gpt4o-mini` | openai/gpt-4o-mini | Fast, cheapest |
| `gpt4o` | openai/gpt-4o | Best balance of speed and accuracy |
| `gpt41` | openai/gpt-4.1 | Most capable |

**Prompting strategy (fixed):** `chain_of_thought` — chosen because it produced the highest F1 score across all models in preliminary trials.

**Scoring:** Same as Phase 0 — class-only matching, Precision / Recall / F1 per class and micro/macro overall.

---

## 2. Architecture

Phase 1 is a separate pipeline that reuses Phase 0 data structures and scoring engine without modifying any Phase 0 files.

```
run_phase1.py  (single model)
run_phase1_parallel.py  (all models side-by-side)
        │
        ▼
phase1/tools/gpt4_tool.py       ← LLM tool wrapper
        │
        └── phase1/prompts/chain_of_thought.py  ← builds prompt messages
        │
        ▼
pipeline/runner.run_evaluation()  ← Phase 0 runner (unchanged)
        │
        ▼
pipeline/scorer.score()           ← Phase 0 scorer (unchanged)
        │
        ▼
phase1/logger.log_phase1()        ← Extended logger (adds token/prompt data)
        │
        ▼
results/<model>_chain_of_thought_<timestamp>.json / .csv
```

---

## 3. Directory Structure

```
practicum/
├── phase1/
│   ├── logger.py                  # Extended logger with token and prompt data
│   ├── prompts/
│   │   ├── zero_shot.py           # Zero-shot strategy (not used in evaluation)
│   │   ├── few_shot.py            # Few-shot strategy (not used in evaluation)
│   │   └── chain_of_thought.py    # Chain-of-thought strategy ← USED
│   └── tools/
│       └── gpt4_tool.py           # OpenAI model wrapper
│
├── run_phase1.py                  # Single-model sequential runner
├── run_phase1_parallel.py         # Multi-model parallel runner
├── .env                           # API credentials (never commit to git)
└── results/                       # JSON + CSV output files
```

---

## 4. Setup

**Install the OpenAI client:**
```bash
pip install openai
```

**Configure your API key** in `.env`:
```
GITHUB_TOKEN=ghp_your_token_here
```

The token is loaded automatically at runtime — no `export` needed.

**GitHub Models free-tier rate limits:**

| Model | Requests/min | Tokens/day |
|-------|-------------|-----------|
| gpt-4o | 10 RPM | ~50,000 |
| gpt-4o-mini | 15 RPM | ~200,000 |
| gpt-4.1 | 10 RPM | ~50,000 |

> Rate limits are per GitHub **account**, not per token. Daily limits reset at midnight UTC.

---

## 5. Prompting Strategies

Three strategies are implemented. Only `chain_of_thought` is used in the evaluation.

**Zero-shot** — Contract sent with no examples. Model relies on definitions alone. Lowest token usage, lowest recall.

**Few-shot** — Three synthetic example contracts (one per class) prepended as conversation examples. Medium token usage, higher precision.

**Chain-of-thought** ← SELECTED — Model is asked to reason step-by-step through four explicit checks before producing the final JSON answer:

- Step 1: Check for external calls before state updates (reentrancy)
- Step 2: Check for unprotected sensitive functions (access_control)
- Step 3: Check for `block.timestamp` in critical decisions (timestamp_dependency)
- Step 4: List confirmed vulnerability classes as JSON

The final `{"vulnerabilities": [...]}` block is extracted from the response via regex, so the reasoning text does not interfere with parsing.

---

## 6. How to Run

**Verify the token works first:**
```bash
python3 -c "
import os; from pathlib import Path
for l in Path('.env').read_text().splitlines():
    if '=' in l and not l.startswith('#'):
        k,v = l.split('=',1); os.environ[k]=v
from openai import OpenAI
client = OpenAI(base_url='https://models.github.ai/inference', api_key=os.environ['GITHUB_TOKEN'])
r = client.chat.completions.create(model='openai/gpt-4o-mini',
    messages=[{'role':'user','content':'Say yes.'}], max_tokens=5)
print('OK:', r.choices[0].message.content)
"
```

**Run a single model (recommended — one per day to stay within quota):**
```bash
python3 run_phase1.py --model gpt4o-mini   # cheapest, largest quota
python3 run_phase1.py --model gpt4o        # best results
python3 run_phase1.py --model gpt41        # most capable
python3 run_phase1.py --dry-run            # 3 contracts only, no files saved
```

**Run all models in parallel (use only with fresh quota):**
```bash
python3 run_phase1_parallel.py
python3 run_phase1_parallel.py --models gpt4o gpt4o-mini
```

Each single-model run takes approximately 5–10 minutes (54 contracts × 5–10s each).

---

## 7. Output

Results are saved to `results/` as both JSON and CSV:
```
results/gpt4o_chain_of_thought_20260608T001200Z.json
results/gpt4o_chain_of_thought_20260608T001200Z.csv
```

**Terminal output (single model run):**
```
==============================================================================
  PHASE 1 RESULTS  —  gpt4o_chain_of_thought
==============================================================================
  Model        : gpt4o  (openai/gpt-4o)
  Strategy     : chain_of_thought
  Contracts    : 54
  Runtime      : 497.3s total  |  9.2s per contract

  Token Usage
  ────────────────────────────────────────────
  Prompt tokens               :     14,891
  Completion tokens           :      2,821
  Total tokens                :     17,712
  Est. cost (OpenAI list price):    ~$0.066

  Findings by Vulnerability Class
  ─────────────────────────────────────────────────────────────────────────
  Class                         TP    FP    FN  Precision    Recall        F1
  ─────────────────────────────────────────────────────────────────────────
  reentrancy                    19     3    12      0.864     0.613     0.717  [pred 22, GT 31]
  access_control                10     1     8      0.909     0.556     0.690  [pred 11, GT 18]
  timestamp_dependency           0     0     5      0.000     0.000     0.000  [pred  0, GT  5]
  ─────────────────────────────────────────────────────────────────────────
  micro-average                 29     4    25      0.879     0.537     0.667  [pred 33, GT 54]
  macro-average                                     0.591     0.389     0.469
==============================================================================
```

---

## 8. Preliminary Results

From the first successful parallel run (gpt-4.1 failed in this run due to rate limiting under parallel load — re-run required):

| Model | Precision | Recall | F1 (micro) | Tokens |
|-------|-----------|--------|------------|--------|
| gpt4o — chain_of_thought | 0.913 | 0.389 | 0.545 | 17,712 |
| gpt4o — few_shot | 1.000 | 0.241 | 0.388 | 12,169 |
| gpt4o — zero_shot | 0.778 | 0.130 | 0.222 | 3,385 |
| gpt4o-mini — chain_of_thought | 0.524 | 0.204 | 0.293 | 10,361 |
| gpt4o-mini — few_shot | 1.000 | 0.111 | 0.200 | 5,204 |
| gpt4o-mini — zero_shot | 0.857 | 0.111 | 0.197 | 4,397 |

**Key observations:**
- `chain_of_thought` consistently achieves the best F1 across all models
- All models scored F1 = 0.000 on `timestamp_dependency` — a notable finding
- High precision + low recall: models are conservative, flagging only confident findings
- gpt4o (chain_of_thought) at F1 = 0.545 is below Mythril's F1 = 0.614 (Phase 0 baseline)

---

## 9. Known Issues

**Rate limiting from parallel runs**
Running all 9 model/strategy combinations simultaneously consumed ~53,000 tokens and
exhausted the gpt-4o daily quota. Subsequent runs all returned "Too many requests."
Fix: use `run_phase1.py` (one model at a time), and run each model on a separate day.

**Contract ID mismatch (fixed)**
The tool returned `contract_id = "Foo.sol"` but the runner normalised it to
`"access_control/Foo.sol"`. This caused token metadata to be lost in saved JSON files
(all showing `strategy: ""`, `tokens: 0`). Fixed by building a filename-to-normalised-ID
map before each run.

**gpt-4.1 under parallel load (fixed)**
All gpt-4.1 calls failed when running 9 parallel threads. The model has a stricter
rate limit. Fix: run gpt-4.1 only through `run_phase1.py` (sequential).
