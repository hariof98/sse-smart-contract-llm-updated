"""
Moderator behaviour analysis (Phase 3) — no API calls.

Reads the saved Phase 3 run outputs for one run-name and reports, aggregated
across every contract (and every run file present):

  * Findings per specialist BEFORE the moderator.
  * Findings AFTER the moderator (the final list).
  * Kept   — a specialist finding the moderator retained.
  * Dropped — a specialist finding the moderator removed.
  * Added  — a moderator finding no specialist reported.
  * Merged — duplicate specialist findings collapsed.
  * Moderator override rate — how much of the specialists' work the moderator
    changed (if > ~50%, the specialists aren't contributing).
  * Per-class recall for each specialist against ground truth (e.g. the
    reentrancy specialist's recall on reentrancy contracts).

Usage
-----
    python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour --run-name <name>
    python3 -m phases.phase3_multi_agent.reporting.moderator_behaviour \
        --results-dir results/phase3_multi_agent/<name>
"""

import argparse
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import VULNERABILITY_CLASSES

_RESULTS_ROOT = _project_root / "results" / "phase3_multi_agent"
_SPECIALIST_CLASSES = list(VULNERABILITY_CLASSES)


def _load_run_files(run_dir: Path) -> list[dict]:
    """Load every per-run result JSON in *run_dir* (excludes variance.json)."""
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
            payloads.append((f.name, json.loads(f.read_text(encoding="utf-8"))))
        except json.JSONDecodeError:
            print(f"  [warn] skipping unreadable JSON: {f.name}")
    return payloads


def analyse(payloads: list[tuple[str, dict]]) -> dict:
    """Aggregate moderator-behaviour statistics across all run payloads."""
    before_per_spec = {c: 0 for c in _SPECIALIST_CLASSES}
    after_total = 0
    kept = dropped = added = merged = 0
    union_total = 0                 # distinct specialist findings (base for override rate)
    contracts_seen = 0
    contracts_changed = 0
    skipped = 0

    # Per-specialist recall vs ground truth.
    recall_num = {c: 0 for c in _SPECIALIST_CLASSES}
    recall_den = {c: 0 for c in _SPECIALIST_CLASSES}

    for _fname, payload in payloads:
        for entry in payload.get("contracts", []):
            contracts_seen += 1
            if entry.get("skipped"):
                skipped += 1

            gt = set(entry.get("gt_classes", []))
            final = set(entry.get("pred_classes", []))
            union = set(entry.get("specialist_union_classes", []))
            specialists = entry.get("specialists", {}) or {}

            spec_classes = {
                c: set((specialists.get(c) or {}).get("classes", []))
                for c in _SPECIALIST_CLASSES
            }
            specialist_total = sum(len(v) for v in spec_classes.values())

            for c in _SPECIALIST_CLASSES:
                before_per_spec[c] += len(spec_classes[c])
            after_total += len(final)

            kept    += len(union & final)
            dropped += len(union - final)
            added   += len(final - union)
            merged  += specialist_total - len(union)   # duplicates collapsed
            union_total += len(union)

            if union != final:
                contracts_changed += 1

            # Recall: for each specialist class present in ground truth, did the
            # matching specialist report it?
            for c in _SPECIALIST_CLASSES:
                if c in gt:
                    recall_den[c] += 1
                    if c in spec_classes[c]:
                        recall_num[c] += 1

    override_changes = dropped + added
    override_rate = (override_changes / union_total) if union_total else 0.0
    contract_change_rate = (contracts_changed / contracts_seen) if contracts_seen else 0.0

    return {
        "n_run_files": len(payloads),
        "contracts_seen": contracts_seen,
        "skipped": skipped,
        "before_per_spec": before_per_spec,
        "before_total": sum(before_per_spec.values()),
        "after_total": after_total,
        "kept": kept,
        "dropped": dropped,
        "added": added,
        "merged": merged,
        "union_total": union_total,
        "override_changes": override_changes,
        "override_rate": override_rate,
        "contracts_changed": contracts_changed,
        "contract_change_rate": contract_change_rate,
        "recall_num": recall_num,
        "recall_den": recall_den,
    }


def _print_report(run_name: str, stats: dict) -> None:
    sep = "=" * 78
    print()
    print(sep)
    print(f"  MODERATOR BEHAVIOUR  —  {run_name}")
    print(sep)
    print(f"  Run files analysed : {stats['n_run_files']}")
    print(f"  Contract-runs      : {stats['contracts_seen']}"
          + (f"  ({stats['skipped']} skipped by token cap)" if stats["skipped"] else ""))

    print()
    print("  Findings before the moderator (per specialist)")
    print(f"  {'-'*54}")
    for c in _SPECIALIST_CLASSES:
        print(f"  {c:<32}: {stats['before_per_spec'][c]:>6}")
    print(f"  {'TOTAL (before)':<32}: {stats['before_total']:>6}")
    print(f"  {'Final list (after moderator)':<32}: {stats['after_total']:>6}")

    print()
    print("  Moderator edits (vs specialist union)")
    print(f"  {'-'*54}")
    print(f"  {'Kept (retained)':<32}: {stats['kept']:>6}")
    print(f"  {'Dropped (removed)':<32}: {stats['dropped']:>6}")
    print(f"  {'Added (no specialist had it)':<32}: {stats['added']:>6}")
    print(f"  {'Merged (duplicates collapsed)':<32}: {stats['merged']:>6}")

    print()
    print("  Override rate")
    print(f"  {'-'*54}")
    print(f"  {'Findings changed / specialist base':<40}: "
          f"{stats['override_changes']} / {stats['union_total']}  "
          f"= {stats['override_rate']*100:.1f}%")
    print(f"  {'Contracts the moderator changed':<40}: "
          f"{stats['contracts_changed']} / {stats['contracts_seen']}  "
          f"= {stats['contract_change_rate']*100:.1f}%")
    if stats["override_rate"] > 0.5:
        print("  [!] Override rate > 50% — specialists may not be contributing much.")

    print()
    print("  Per-specialist recall vs ground truth")
    print(f"  {'-'*54}")
    print(f"  {'Specialist':<32} {'Recall':>8}   (hits / class contracts)")
    for c in _SPECIALIST_CLASSES:
        den = stats["recall_den"][c]
        num = stats["recall_num"][c]
        rec = (num / den) if den else 0.0
        print(f"  {c:<32} {rec:>8.3f}   ({num} / {den})")
    print(sep)
    print("  Note: compare each specialist's recall to the Phase 1 single-agent")
    print("  recall on the SAME class. If a specialist does not beat the single")
    print("  agent on its own class, class-specialisation is not paying off.")
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyse Phase 3 moderator behaviour from saved run outputs.",
    )
    parser.add_argument("--run-name", default=None,
                        help="Run subfolder name under results/phase3_multi_agent/.")
    parser.add_argument("--results-dir", default=None,
                        help="Explicit path to the run directory (overrides --run-name).")
    args = parser.parse_args()

    if args.results_dir:
        run_dir = Path(args.results_dir)
        run_name = run_dir.name
    elif args.run_name:
        run_dir = _RESULTS_ROOT / args.run_name
        run_name = args.run_name
    else:
        print("  [error] Provide --run-name or --results-dir.")
        print(f"  Available runs under {_RESULTS_ROOT}:")
        if _RESULTS_ROOT.exists():
            for d in sorted(p for p in _RESULTS_ROOT.iterdir() if p.is_dir()):
                print(f"    {d.name}")
        sys.exit(1)

    payloads = _load_run_files(run_dir)
    stats = analyse(payloads)
    _print_report(run_name, stats)


if __name__ == "__main__":
    main()
