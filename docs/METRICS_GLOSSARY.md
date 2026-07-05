# Metrics Glossary

Reference for all evaluation metrics used in the result JSON files.

---

## Confusion Matrix Terms

Every contract is evaluated per vulnerability class. For each class, the model's prediction is compared against the ground truth label, producing one of four outcomes:

| Term | Full Name | Meaning |
|---|---|---|
| **TP** | True Positive | The model **correctly predicted** the vulnerability is present. Ground truth says *yes*, model says *yes*. |
| **FP** | False Positive | The model **incorrectly predicted** the vulnerability is present. Ground truth says *no*, model says *yes*. A "false alarm". |
| **FN** | False Negative | The model **missed** a vulnerability that is present. Ground truth says *yes*, model says *no*. A "miss". |
| **TN** | True Negative | The model **correctly predicted** no vulnerability. Ground truth says *no*, model says *no*. (Not tracked in our results because only in-scope positive labels are evaluated.) |

### Example

A contract in the `reentrancy/` folder is analysed. The model predicts `["reentrancy", "access_control"]`.

- `reentrancy` → **TP** (correctly detected)
- `access_control` → **FP** (false alarm — the ground truth only has `reentrancy`)

If the model had predicted `[]` (nothing), then `reentrancy` would be a **FN** (missed).

---

## Performance Metrics

These are computed from the TP, FP, and FN counts above.

### Precision

$$\text{Precision} = \frac{TP}{TP + FP}$$

*"Of everything the model flagged, how much was correct?"*

- High precision = few false alarms.
- A precision of 1.0 means every prediction the model made was correct (but it may have missed some).

### Recall

$$\text{Recall} = \frac{TP}{TP + FN}$$

*"Of all the real vulnerabilities, how many did the model find?"*

- High recall = few misses.
- A recall of 1.0 means the model found every vulnerability (but it may have raised false alarms).

### F1 Score

$$\text{F1} = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$$

*"The harmonic mean of precision and recall — a single balanced score."*

- Ranges from 0 (worst) to 1 (perfect).
- Penalises models that are strong in one metric but weak in the other.
- F1 = 1.0 only when both precision and recall are 1.0.

---

## Aggregation Methods

Results are reported per class (e.g. `reentrancy`, `access_control`, `timestamp_dependency`) and then aggregated into overall scores using two methods:

### Micro-Average

Pools all TP, FP, and FN counts across all classes into a single set, then computes precision, recall, and F1 from the totals.

$$\text{Micro-Precision} = \frac{\sum TP}{\sum TP + \sum FP}$$

- **Weights each contract equally** — classes with more contracts (e.g. `reentrancy` with 31) have more influence than smaller classes (e.g. `timestamp_dependency` with 5).
- Best reflects overall accuracy across the full dataset.

### Macro-Average

Computes precision, recall, and F1 independently for each class, then takes the unweighted mean.

$$\text{Macro-Precision} = \frac{1}{N}\sum_{i=1}^{N} \text{Precision}_i$$

- **Weights each class equally** — a class with 5 contracts counts the same as a class with 31.
- Better reflects performance on rare/underrepresented vulnerability types.
- A model that excels on `reentrancy` but fails on `timestamp_dependency` will have a lower macro score than micro score.

---

## Result JSON Structure

Each result file (e.g. `gpt41-nano_chain_of_thought_20260614T174012Z.json`) contains:

| Field | Description |
|---|---|
| `tool` | Model and strategy identifier (e.g. `gpt41-nano_chain_of_thought`) |
| `num_contracts` | Total contracts evaluated (54) |
| `total_runtime_seconds` | Wall-clock time for the full run |
| `mean_runtime_seconds` | Average time per contract |
| `per_class` | TP/FP/FN/precision/recall/F1 broken down by vulnerability class |
| `overall.micro` | Micro-averaged metrics across all classes |
| `overall.macro` | Macro-averaged metrics across all classes |
| `contracts` | Per-contract detail: ground truth, predictions, token usage, full LLM response |

### Per-Contract Fields

| Field | Description |
|---|---|
| `contract_id` | Path relative to the dataset root (e.g. `reentrancy/simple_dao.sol`) |
| `gt_classes` | Ground truth vulnerability classes for this contract |
| `pred_classes` | Classes predicted by the model |
| `tp` / `fp` / `fn` | Which classes were true positives, false positives, or false negatives |
| `runtime_seconds` | Time taken for this single API call |
| `prompt_tokens` | Tokens in the input prompt |
| `completion_tokens` | Tokens in the model's response |
| `total_tokens` | Sum of prompt + completion tokens |
| `response` | The model's full text response (including reasoning for chain-of-thought) |
