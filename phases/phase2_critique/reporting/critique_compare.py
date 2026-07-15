"""
Detector-vs-Critic comparison for a Phase 2 result file.

Phase 2's run report only scores the FINAL (post-critic) prediction. This tool
re-reads a saved Phase 2 results JSON and reconstructs TWO scored views from
the per-contract data it already contains:

    * Detector-only   — score the detector's classes (what Phase 1 would give)
    * After-Critic    — score the critic's final classes (what Phase 2 gives)

It then reports the before/after delta in precision / recall / F1 (per class and
overall), the critic's behaviour, and a per-contract breakdown of exactly what
the critic changed and whether it helped or hurt.

No API calls — pure re-analysis of an existing run.

Usage
-----
    python3 reporting/critique_compare.py                       # newest critique_*.json
    python3 reporting/critique_compare.py results/<file>.json   # a specific run
"""

import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import GroundTruth, Prediction, Vulnerability, VULNERABILITY_CLASSES
from shared.core.scorer import score, ScorerReport

_RESULTS_DIR = _project_root / "results" / "phase2_critique"


def _latest_results() -> Path:
    candidates = sorted(_RESULTS_DIR.glob("critique_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No critique_*.json found in {_RESULTS_DIR}. Pass a path explicitly."
        )
    return candidates[-1]


def _pairs(contracts: list[dict], classes_key: str) -> list[tuple[GroundTruth, Prediction]]:
    """Rebuild (GroundTruth, Prediction) pairs from saved per-contract classes."""
    pairs = []
    for c in contracts:
        gt = GroundTruth(
            contract_id=c["contract_id"],
            contract_path="",
            vulnerabilities=[Vulnerability(vuln_class=x) for x in c.get("gt_classes", [])],
        )
        pred = Prediction(
            contract_id=c["contract_id"],
            tool_name=classes_key,
            vulnerabilities=[Vulnerability(vuln_class=x) for x in c.get(classes_key, [])],
        )
        pairs.append((gt, pred))
    return pairs


def _contract_effect(gt: set, detector: set, critic: set) -> str:
    """One-word verdict on what the critic's edits did for this contract."""
    if detector == critic:
        return "same"
    removed = detector - critic
    added = critic - detector
    good = len(removed - gt) + len(added & gt)   # dropped FP / added TP
    bad = len(removed & gt) + len(added - gt)    # dropped TP / added FP
    if bad and good:
        return "mixed"
    if bad:
        return "hurt"
    if good:
        return "helped"
    return "changed"


def _fmt_delta(before: float, after: float) -> str:
    d = after - before
    if abs(d) < 1e-9:
        return "  ·   "
    return f"{d:+.3f}"


def _metrics_block(title: str, det: ScorerReport, fin: ScorerReport) -> list[str]:
    lines = [title, ""]
    header = (f"| {'Class':<22} | {'Detector':>20} | {'After-Critic':>20} | {'ΔF1':>7} |")
    sub =    (f"| {'':<22} | {'P':>6} {'R':>6} {'F1':>6} | {'P':>6} {'R':>6} {'F1':>6} | {'':>7} |")
    rule =   f"|{'-'*24}|{'-'*22}|{'-'*22}|{'-'*9}|"
    lines += [header, sub, rule]
    for cls in VULNERABILITY_CLASSES:
        dcm, fcm = det.per_class[cls], fin.per_class[cls]
        lines.append(
            f"| {cls:<22} | "
            f"{dcm.precision:>6.3f} {dcm.recall:>6.3f} {dcm.f1:>6.3f} | "
            f"{fcm.precision:>6.3f} {fcm.recall:>6.3f} {fcm.f1:>6.3f} | "
            f"{_fmt_delta(dcm.f1, fcm.f1):>7} |"
        )
    lines.append(rule)
    do, fo = det.overall, fin.overall
    lines.append(
        f"| {'micro-average':<22} | "
        f"{do.micro_precision:>6.3f} {do.micro_recall:>6.3f} {do.micro_f1:>6.3f} | "
        f"{fo.micro_precision:>6.3f} {fo.micro_recall:>6.3f} {fo.micro_f1:>6.3f} | "
        f"{_fmt_delta(do.micro_f1, fo.micro_f1):>7} |"
    )
    lines.append(
        f"| {'macro-average':<22} | "
        f"{do.macro_precision:>6.3f} {do.macro_recall:>6.3f} {do.macro_f1:>6.3f} | "
        f"{fo.macro_precision:>6.3f} {fo.macro_recall:>6.3f} {fo.macro_f1:>6.3f} | "
        f"{_fmt_delta(do.macro_f1, fo.macro_f1):>7} |"
    )
    return lines


def _counts_block(det: ScorerReport, fin: ScorerReport) -> list[str]:
    lines = ["Confusion counts (Detector -> After-Critic)", ""]
    lines.append(f"| {'Class':<22} | {'TP':>9} | {'FP':>9} | {'FN':>9} |")
    lines.append(f"|{'-'*24}|{'-'*11}|{'-'*11}|{'-'*11}|")
    for cls in VULNERABILITY_CLASSES:
        d, f = det.per_class[cls], fin.per_class[cls]
        lines.append(
            f"| {cls:<22} | {d.tp:>3} -> {f.tp:<3} | {d.fp:>3} -> {f.fp:<3} | {d.fn:>3} -> {f.fn:<3} |"
        )
    do, fo = det.overall, fin.overall
    lines.append(f"|{'-'*24}|{'-'*11}|{'-'*11}|{'-'*11}|")
    lines.append(
        f"| {'TOTAL (micro)':<22} | {do.micro_tp:>3} -> {fo.micro_tp:<3} | "
        f"{do.micro_fp:>3} -> {fo.micro_fp:<3} | {do.micro_fn:>3} -> {fo.micro_fn:<3} |"
    )
    return lines


def build_report(results_path: Path) -> tuple[str, list[dict]]:
    data = json.loads(results_path.read_text(encoding="utf-8"))
    contracts = data["contracts"]
    n = len(contracts)

    det = score(_pairs(contracts, "detector_classes"))
    fin = score(_pairs(contracts, "critic_classes"))

    # Error / fallback accounting
    critic_errors = sum(1 for c in contracts if c.get("critic_error"))
    detector_errors = sum(1 for c in contracts if c.get("detector_error"))
    n_with_vuln = sum(1 for c in contracts if c.get("gt_classes"))

    # Per-contract rows
    rows: list[dict] = []
    effect_counts = {"same": 0, "helped": 0, "hurt": 0, "mixed": 0, "changed": 0}
    for c in contracts:
        gt = set(c.get("gt_classes", []))
        d = set(c.get("detector_classes", []))
        f = set(c.get("critic_classes", []))
        effect = _contract_effect(gt, d, f)
        effect_counts[effect] += 1
        rows.append({
            "contract_id": c["contract_id"],
            "actual_vuln": "|".join(sorted(gt)) or "(none)",
            "detector_pred": "|".join(sorted(d)) or "(none)",
            "detector_correct": int(d == gt),
            "critic_pred": "|".join(sorted(f)) or "(none)",
            "critic_correct": int(f == gt),
            "removed_by_critic": "|".join(c.get("removed", [])),
            "added_by_critic": "|".join(c.get("added", [])),
            "effect": effect,
            "critic_failed": int(bool(c.get("critic_error"))),
        })

    det_correct = sum(r["detector_correct"] for r in rows)
    crit_correct = sum(r["critic_correct"] for r in rows)

    # ── Assemble markdown ──────────────────────────────────────────────────
    L: list[str] = []
    L.append(f"# Phase 2 — Detector vs Critic comparison")
    L.append("")
    L.append(f"Source: `{results_path.name}`  ")
    L.append(f"Tool: `{data['tool']}`")
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append(f"- Contracts evaluated: **{n}**  (with a real vulnerability: {n_with_vuln})")
    L.append(f"- Exactly-correct contracts: detector **{det_correct}/{n}** -> after-critic **{crit_correct}/{n}**")
    L.append(f"- Pipeline errors: critic failed on **{critic_errors}** "
             f"(fell back to detector output), detector failed on **{detector_errors}**")
    L.append(f"- Per-contract effect of the critic: "
             f"helped **{effect_counts['helped']}**, hurt **{effect_counts['hurt']}**, "
             f"mixed **{effect_counts['mixed']}**, no change **{effect_counts['same']}**")
    L.append("")
    L.append("> Note: the `critic failed` contracts could not be revised, so their")
    L.append("> 'after-critic' value equals the detector value. The true effect of")
    L.append("> critique is best read on the contracts where it actually ran.")
    L.append("")
    L.append("## Metrics before vs after critique")
    L.append("")
    L += _metrics_block("", det, fin)
    L.append("")
    L += _counts_block(det, fin)
    L.append("")
    L.append("## Per-contract breakdown")
    L.append("")
    L.append(f"| # | Contract | Actual | Detector | det✓ | After-Critic | crit✓ | Removed | Added | Effect |")
    L.append(f"|--:|---|---|---|:--:|---|:--:|---|---|---|")
    for i, r in enumerate(rows, 1):
        flag = " ⚠" if r["critic_failed"] else ""
        L.append(
            f"| {i} | `{r['contract_id']}` | {r['actual_vuln']} | {r['detector_pred']} | "
            f"{'✓' if r['detector_correct'] else '✗'} | {r['critic_pred']} | "
            f"{'✓' if r['critic_correct'] else '✗'} | {r['removed_by_critic'] or '·'} | "
            f"{r['added_by_critic'] or '·'} | {r['effect']}{flag} |"
        )
    L.append("")
    L.append("Legend: det✓ / crit✓ = prediction exactly matches ground truth. "
             "⚠ = critic call failed (after-critic = detector fallback).")
    L.append("")

    return "\n".join(L), rows


def main() -> None:
    results_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _latest_results()
    if not results_path.exists():
        print(f"File not found: {results_path}")
        sys.exit(1)

    report_md, rows = build_report(results_path)

    # Write markdown + CSV next to the source file
    stem = results_path.stem
    md_path = results_path.with_name(f"{stem}_comparison.md")
    csv_path = results_path.with_name(f"{stem}_comparison.csv")
    md_path.write_text(report_md, encoding="utf-8")

    import csv as _csv
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Print the markdown to the console too
    print(report_md)
    print(f"Saved:\n  {md_path}\n  {csv_path}")


if __name__ == "__main__":
    main()
