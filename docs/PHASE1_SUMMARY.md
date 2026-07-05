# Phase 1 Summary — LLM Evaluation for Smart Contract Vulnerability Detection

**Project:** MSc Practicum
**Author:** [Your Name]
**Date:** June 2026

---

## What We Did

In Phase 1, we extended the evaluation pipeline built in Phase 0 to assess how well Large Language Models (LLMs) can detect vulnerabilities in Solidity smart contracts. Rather than running a static analysis tool, we sent each contract's source code directly to an LLM and asked it to identify which vulnerability classes were present.

We evaluated three OpenAI models — GPT-4o Mini, GPT-4o, and GPT-4.1 — across the same 54 contracts from the SmartBugs Curated dataset used in Phase 0. The three vulnerability classes under evaluation were reentrancy, access_control, and timestamp_dependency.

---

## How It Works

Each contract is submitted to the LLM via the GitHub Models inference API. The model reads the Solidity source code and returns a structured JSON response identifying which vulnerability classes it detected. For example:

```json
{"vulnerabilities": ["reentrancy", "access_control"]}
```

These predictions are then scored against the ground truth labels using the same Precision, Recall, and F1 metrics from Phase 0.

---

## Prompting Strategy

We designed and tested three prompting strategies:

**Zero-shot** — The contract is sent with no examples. The model relies only on the vulnerability definitions provided in the system prompt. This used the fewest tokens but produced the lowest recall.

**Few-shot** — Three hand-crafted example contracts (one per vulnerability class) are shown to the model before the target contract. This improved precision but recall remained low.

**Chain-of-Thought** — The model is explicitly asked to reason through each vulnerability class step by step before giving its final answer. This produced the highest F1 scores across all models and was selected as the evaluation strategy.

The chain-of-thought prompt guides the model through four steps: checking for reentrancy, checking for access control issues, checking for timestamp dependency, and then listing confirmed vulnerabilities in JSON format.

---

## Models Evaluated

| Model | API Identifier | Notes |
|-------|---------------|-------|
| GPT-4o Mini | openai/gpt-4o-mini | Fastest, lowest cost |
| GPT-4o | openai/gpt-4o | Best balance of speed and accuracy |
| GPT-4.1 | openai/gpt-4.1 | Most capable model available |

All models were accessed via the GitHub Models inference API using a GitHub Personal Access Token stored in a local `.env` file.

---

## Preliminary Results

The table below shows results from the first successful evaluation run. The chain-of-thought strategy was used for all models. Note that GPT-4.1 results are marked as pending — all API calls failed during a parallel execution run due to rate limiting and a clean re-run is required.

| Model | Precision | Recall | F1 Score | Tokens Used |
|-------|-----------|--------|----------|-------------|
| GPT-4o | 0.913 | 0.389 | 0.545 | 17,712 |
| GPT-4o Mini | 0.524 | 0.204 | 0.293 | 10,361 |
| GPT-4.1 | — | — | — | (re-run needed) |

**Results by vulnerability class (GPT-4o, chain-of-thought):**

| Vulnerability Class | TP | FP | FN | F1 Score |
|--------------------|----|----|----|----------|
| reentrancy | 19 | 3 | 12 | 0.609 |
| access_control | 10 | 1 | 8 | 0.560 |
| timestamp_dependency | 0 | 0 | 5 | 0.000 |

**Comparison with Phase 0 baselines:**

| Tool | micro-F1 |
|------|----------|
| Mythril (Phase 0) | 0.614 |
| GPT-4o — chain-of-thought | 0.545 |
| GPT-4o Mini — chain-of-thought | 0.293 |

---

## Key Observations

**1. Chain-of-thought outperforms other strategies.**
Asking the model to reason step by step before committing to an answer consistently produced better F1 scores than zero-shot or few-shot prompting across both models.

**2. All models failed to detect timestamp_dependency.**
Every model scored F1 = 0.000 on timestamp_dependency across all prompting strategies. This is a significant finding — it suggests LLMs struggle to recognise this class without additional guidance or examples specific to it.

**3. High precision, low recall.**
Models tend to be conservative — they only flag vulnerabilities they are highly confident about. This results in good precision (few false positives) but poor recall (many missed vulnerabilities). GPT-4o reached precision of 0.913 but recall of only 0.389.

**4. GPT-4o does not outperform Mythril.**
GPT-4o's micro-F1 of 0.545 is below Mythril's 0.614, suggesting that without prompt tuning or domain-specific fine-tuning, LLMs are not yet competitive with specialised symbolic execution tools on this task.

---

## Challenges Encountered

**API Rate Limiting**
The GitHub Models free tier enforces daily token quotas (approximately 50,000 tokens per day for GPT-4o). Running all model/strategy combinations simultaneously in a parallel execution used ~53,000 tokens and exhausted the daily quota, causing all subsequent runs to fail with "Too many requests." The pipeline was redesigned to run one model at a time to stay within quota limits.

**Contract ID Mismatch**
A bug was discovered where token usage and strategy metadata were not being saved in the result files. The tool was returning a bare filename (e.g. `Foo.sol`) as the contract identifier, while the runner was normalising it to a folder-prefixed path (e.g. `access_control/Foo.sol`). This mismatch meant the metadata could never be matched and attached. The bug was fixed by building an explicit filename-to-normalised-ID map before each run.

---

## Output Files

Each completed run produces two files in the `results/` directory:

- **JSON file** — full metrics (per-class and overall), token counts per contract, the complete model prompt and response for every contract
- **CSV file** — one row per contract with predictions, ground truth labels, match results, and token counts

File naming format: `gpt4o_chain_of_thought_20260608T001200Z.json`

---

## Next Steps

- Complete clean single-model runs for GPT-4o, GPT-4o Mini, and GPT-4.1 (one per day to respect quota limits)
- Investigate why timestamp_dependency is consistently missed — consider adding targeted examples
- Add support for Anthropic Claude and Google Gemini models
- Run evaluation on the SolidiFI dataset
- Compare all results statistically and write the thesis chapter on LLM vs traditional tool performance
