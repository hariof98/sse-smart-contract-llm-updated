"""
Hybrid behaviour analysis (Phase 4) — no API calls.

Reads the saved Phase 4 run outputs for one run-name, plus the cached Phase 0
Slither results and the Phase 1 single-agent results, and produces the RQ2
comparison the write-up requires:

  * Slither findings BEFORE the LLM filter (in-scope) vs AFTER (confirmed).
  * Confirmed / rejected counts per class.
  * Skipped-contract count + skip rate (Slither found nothing → no LLM call).
  * LLM tokens per confirmed finding (cost efficiency).
  * False-positive reduction: how many Slither findings the LLM correctly
    rejected (checked against ground truth) — where the hybrid should win.
  * Three-way comparison table (precision / recall / F1 / tokens) for:
        (a) Slither alone   (Phase 0)
        (b) LLM alone       (Phase 1, same or specified model)
        (c) Slither + LLM   (Phase 4 hybrid, averaged over runs)

Usage
-----
    python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name <name>
    python3 -m phases.phase4_hybrid.reporting.hybrid_behaviour --run-name <name> \
        --model gpt-4o-mini --compare-llm-model gpt-4o
"""

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Optional

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import VULNERABILITY_CLASSES

_RESULTS_ROOT = _project_root / "results" / "phase4_hybrid"
_PHASE0_DIR = _project_root / "results" / "phase0_traditional"
_PHASE1_DIR = _project_root / "results" / "phase1_single_llm"
_CLASSES = list(VULNERABILITY_CLASSES)


# ── file loading helpers ───────────────────────────────────────────────────

def _load_run_files(run_dir: Path) -> list[dict]:
    if not run_dir.exists():
        print(f"  [error] Run directory not found: {run_dir}")
        sys.exit(1)
    files = sorted(f for f in run_dir.glob("*.json") if f.name != "variance.json")
    if not files:
        print(f"  [error] No result JSON files found in {run_dir}")
        sys.exit(1)
    payloads = []
    for f in files:
        try:
            payloads.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            print(f"  [warn] skipping unreadable JSON: {f.name}")
    return payloads


def _latest(glob_dir: Path, pattern: str) -> Optional[Path]:
    if not glob_dir.exists():
        return None
    files = [f for f in glob_dir.glob(pattern) if "_comparison" not in f.name]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _overall_and_perclass(payload: dict) -> dict:
    """Pull overall micro + per-class P/R/F1 from a base-logger payload."""
    ov = payload.get("overall", {}).get("micro", {})
    return {
        "precision": ov.get("precision", 0.0),
        "recall": ov.get("recall", 0.0),
        "f1": ov.get("f1", 0.0),
        "per_class": payload.get("per_class", {}),
        "tokens": payload.get("total_tokens_used", 0),
        "num_contracts": payload.get("num_contracts", 0),
    }


# ── hybrid behaviour (from Phase 4 per-contract raw) ────────────────────────

def analyse_hybrid(payloads: list[dict]) -> dict:
    confirmed_per_class = {c: 0 for c in _CLASSES}
    rejected_per_class = {c: 0 for c in _CLASSES}
    in_scope_total = 0
    confirmed_total = 0
    rejected_total = 0
    fp_rejected = 0        # correctly rejected (not in ground truth)
    tp_rejected = 0        # wrongly rejected (was in ground truth)
    contracts_seen = 0
    skipped = 0
    tokens = 0

    # Average overall/per-class F1 across the run payloads.
    micro_f1s: list[float] = []
    micro_p: list[float] = []
    micro_r: list[float] = []
    per_class_f1: dict[str, list[float]] = {c: [] for c in _CLASSES}

    for payload in payloads:
        oc = _overall_and_perclass(payload)
        micro_f1s.append(oc["f1"]); micro_p.append(oc["precision"]); micro_r.append(oc["recall"])
        for c in _CLASSES:
            per_class_f1[c].append(oc["per_class"].get(c, {}).get("f1", 0.0))
        tokens += payload.get("total_tokens_used", 0)

        for entry in payload.get("contracts", []):
            contracts_seen += 1
            if entry.get("skipped_llm"):
                skipped += 1
            gt = set(entry.get("gt_classes", []))
            in_scope = entry.get("slither_in_scope_findings", []) or []
            confirmed = entry.get("confirmed_classes", []) or []
            rejected = entry.get("rejected_classes", []) or []

            in_scope_total += len(in_scope)
            confirmed_total += len(confirmed)
            rejected_total += len(rejected)
            for c in confirmed:
                if c in confirmed_per_class:
                    confirmed_per_class[c] += 1
            for c in rejected:
                if c in rejected_per_class:
                    rejected_per_class[c] += 1
                if c in gt:
                    tp_rejected += 1     # bad: dropped a real bug
                else:
                    fp_rejected += 1     # good: dropped a false positive

        # count is per payload; keep last num_contracts
    n_contracts = payloads[0].get("num_contracts", 0) if payloads else 0
    runs = len(payloads)

    return {
        "runs": runs,
        "n_contracts": n_contracts,
        "contracts_seen": contracts_seen,
        "skipped": skipped,
        "skip_rate": (skipped / contracts_seen) if contracts_seen else 0.0,
        "in_scope_total": in_scope_total,
        "confirmed_total": confirmed_total,
        "rejected_total": rejected_total,
        "confirmed_per_class": confirmed_per_class,
        "rejected_per_class": rejected_per_class,
        "fp_rejected": fp_rejected,
        "tp_rejected": tp_rejected,
        "tokens": tokens,
        "mean_micro_f1": statistics.mean(micro_f1s) if micro_f1s else 0.0,
        "std_micro_f1": statistics.stdev(micro_f1s) if len(micro_f1s) > 1 else 0.0,
        "mean_micro_p": statistics.mean(micro_p) if micro_p else 0.0,
        "mean_micro_r": statistics.mean(micro_r) if micro_r else 0.0,
        "mean_per_class_f1": {c: (statistics.mean(v) if v else 0.0) for c, v in per_class_f1.items()},
    }


def _print_report(run_name: str, hyb: dict, slither: Optional[dict],
                  llm: Optional[dict], llm_model: str, hybrid_model: str) -> None:
    sep = "=" * 78
    print()
    print(sep)
    print(f"  HYBRID BEHAVIOUR  —  {run_name}")
    print(sep)
    print(f"  Runs analysed      : {hyb['runs']}  ({hyb['contracts_seen']} contract-runs)")

    print()
    print("  Slither findings through the filter")
    print(f"  {'-'*54}")
    print(f"  {'In-scope (before LLM)':<32}: {hyb['in_scope_total']:>6}")
    print(f"  {'Confirmed (after LLM)':<32}: {hyb['confirmed_total']:>6}")
    print(f"  {'Rejected by LLM':<32}: {hyb['rejected_total']:>6}")
    for c in _CLASSES:
        print(f"    {c:<24} confirmed={hyb['confirmed_per_class'][c]:>3}  "
              f"rejected={hyb['rejected_per_class'][c]:>3}")

    print()
    print("  Efficiency & false-positive reduction")
    print(f"  {'-'*54}")
    print(f"  {'Contracts skipped (no LLM call)':<40}: "
          f"{hyb['skipped']} / {hyb['contracts_seen']}  = {hyb['skip_rate']*100:.1f}%")
    tok_per_conf = (hyb['tokens'] / hyb['confirmed_total']) if hyb['confirmed_total'] else 0
    print(f"  {'LLM tokens per confirmed finding':<40}: {tok_per_conf:>8.1f}")
    print(f"  {'False positives correctly rejected':<40}: {hyb['fp_rejected']}  (good)")
    print(f"  {'True positives wrongly rejected':<40}: {hyb['tp_rejected']}  (bad)")

    # ── Three-way comparison ──────────────────────────────────────────────
    print()
    print("  Three-way comparison (micro-average)")
    print(f"  {'-'*72}")
    print(f"  {'Configuration':<28} {'Prec':>7} {'Recall':>7} {'F1':>7} {'Tokens':>10} {'Tok/contract':>13}")
    print(f"  {'-'*72}")

    def _row(label, p, r, f1, tokens, ncontracts):
        tpc = (tokens / ncontracts) if ncontracts else 0
        print(f"  {label:<28} {p:>7.3f} {r:>7.3f} {f1:>7.3f} {tokens:>10,} {tpc:>13,.0f}")

    if slither:
        _row("(a) Slither alone", slither["precision"], slither["recall"],
             slither["f1"], 0, slither["num_contracts"])
    else:
        print("  (a) Slither alone            : [Phase 0 slither results not found]")

    if llm:
        _row(f"(b) LLM alone ({llm_model})", llm["precision"], llm["recall"],
             llm["f1"], llm["tokens"], llm["num_contracts"])
    else:
        print(f"  (b) LLM alone ({llm_model}) : [Phase 1 results not found]")

    # Hybrid tokens are summed over runs — normalise to one run for fair tok/contract.
    hybrid_tokens_one_run = round(hyb["tokens"] / hyb["runs"]) if hyb["runs"] else hyb["tokens"]
    _row(f"(c) Hybrid ({hybrid_model})", hyb["mean_micro_p"], hyb["mean_micro_r"],
         hyb["mean_micro_f1"], hybrid_tokens_one_run, hyb["n_contracts"])
    print(f"  {'-'*72}")
    print(f"  Hybrid micro-F1 across runs: {hyb['mean_micro_f1']:.3f} ± {hyb['std_micro_f1']:.3f}")

    # ── RQ2 verdicts ──────────────────────────────────────────────────────
    print()
    print("  RQ2 read-out")
    print(f"  {'-'*54}")
    if llm:
        delta = hyb["mean_micro_f1"] - llm["f1"]
        verdict = "matches/exceeds" if delta >= -0.005 else "below"
        print(f"  Hybrid ({hybrid_model}) F1 {hyb['mean_micro_f1']:.3f} vs "
              f"LLM-alone ({llm_model}) {llm['f1']:.3f}  →  {verdict}")
        if llm["tokens"] and hybrid_tokens_one_run:
            ratio = hybrid_tokens_one_run / llm["tokens"]
            print(f"  Token ratio (hybrid / LLM-alone): {ratio:.2f}×")
    else:
        print("  [LLM-alone comparison unavailable — run Phase 1 for the model first.]")
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse Phase 4 hybrid behaviour + 3-way comparison (no API calls).",
    )
    parser.add_argument("--run-name", default=None,
                        help="Run subfolder under results/phase4_hybrid/.")
    parser.add_argument("--results-dir", default=None,
                        help="Explicit path to the run directory (overrides --run-name).")
    parser.add_argument("--model", default="gpt-4o-mini",
                        help="Hybrid model label (for display).")
    parser.add_argument("--compare-llm-model", default=None,
                        help="Phase 1 model to use as the 'LLM alone' comparison "
                             "(default: same as --model).")
    parser.add_argument("--slither-results", default=None,
                        help="Path to Phase 0 slither_*.json (default: newest).")
    parser.add_argument("--phase1-results", default=None,
                        help="Path to a Phase 1 <model>_*.json (default: newest for the model).")
    args = parser.parse_args()

    if args.results_dir:
        run_dir = Path(args.results_dir); run_name = run_dir.name
    elif args.run_name:
        run_dir = _RESULTS_ROOT / args.run_name; run_name = args.run_name
    else:
        print("  [error] Provide --run-name or --results-dir.")
        if _RESULTS_ROOT.exists():
            print(f"  Available runs under {_RESULTS_ROOT}:")
            for d in sorted(p for p in _RESULTS_ROOT.iterdir() if p.is_dir()):
                print(f"    {d.name}")
        sys.exit(1)

    hyb = analyse_hybrid(_load_run_files(run_dir))

    # (a) Slither alone — from Phase 0.
    slither_path = Path(args.slither_results) if args.slither_results else _latest(_PHASE0_DIR, "slither_*.json")
    slither = _overall_and_perclass(json.loads(slither_path.read_text(encoding="utf-8"))) if slither_path and slither_path.exists() else None

    # (b) LLM alone — from Phase 1 for the comparison model.
    compare_model = args.compare_llm_model or args.model
    p1_path = Path(args.phase1_results) if args.phase1_results else _latest(_PHASE1_DIR, f"{compare_model}_*.json")
    llm = _overall_and_perclass(json.loads(p1_path.read_text(encoding="utf-8"))) if p1_path and p1_path.exists() else None

    _print_report(run_name, hyb, slither, llm, compare_model, args.model)


if __name__ == "__main__":
    main()
