"""
Sanity-checks for the SmartBugs loader.

Run from the project root:
    python tests/test_loader.py

Exit code 0 means all checks passed.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.datasets.smartbugs_loader import load_smartbugs, FOLDER_TO_CLASS
from shared.core.schema import GroundTruth, Vulnerability, VULNERABILITY_CLASSES


def test_returns_list_of_ground_truth() -> None:
    gts = load_smartbugs()
    assert isinstance(gts, list), "load_smartbugs() must return a list"
    assert len(gts) > 0, "loader returned an empty list"
    for gt in gts:
        assert isinstance(gt, GroundTruth), f"Expected GroundTruth, got {type(gt)}"
    print(f"[PASS] returns {len(gts)} GroundTruth objects")


def test_only_in_scope_classes() -> None:
    gts = load_smartbugs()
    for gt in gts:
        for v in gt.vulnerabilities:
            assert v.vuln_class in VULNERABILITY_CLASSES, (
                f"{gt.contract_id} has unlisted class '{v.vuln_class}'"
            )
    print("[PASS] all vulnerability classes are in VULNERABILITY_CLASSES")


def test_expected_counts() -> None:
    """Check that each mapped folder contributes the right number of contracts.

    Expected counts (from the cloned dataset):
        reentrancy        → 31
        access_control    → 18
        time_manipulation → 5   (mapped to timestamp_dependency)
    """
    expected: dict[str, int] = {
        "reentrancy": 31,
        "access_control": 18,
        "timestamp_dependency": 5,
    }
    gts = load_smartbugs()
    counts: dict[str, int] = {}
    for gt in gts:
        cls = gt.vulnerabilities[0].vuln_class
        counts[cls] = counts.get(cls, 0) + 1

    for cls, expected_n in expected.items():
        actual = counts.get(cls, 0)
        assert actual == expected_n, (
            f"Expected {expected_n} contracts for '{cls}', got {actual}"
        )
        print(f"[PASS] {cls}: {actual} contracts")

    total_expected = sum(expected.values())
    assert len(gts) == total_expected, (
        f"Expected {total_expected} total contracts, got {len(gts)}"
    )
    print(f"[PASS] total: {len(gts)} contracts")


def test_contract_paths_exist() -> None:
    from pathlib import Path
    gts = load_smartbugs()
    missing = [gt for gt in gts if not Path(gt.contract_path).exists()]
    assert not missing, (
        f"{len(missing)} contract paths do not exist on disk:\n"
        + "\n".join(f"  {gt.contract_path}" for gt in missing[:5])
    )
    print(f"[PASS] all {len(gts)} contract paths exist on disk")


def test_contract_ids_unique() -> None:
    gts = load_smartbugs()
    ids = [gt.contract_id for gt in gts]
    assert len(ids) == len(set(ids)), "contract_ids are not unique"
    print(f"[PASS] all {len(ids)} contract_ids are unique")


def test_each_contract_has_one_vulnerability() -> None:
    gts = load_smartbugs()
    for gt in gts:
        assert len(gt.vulnerabilities) == 1, (
            f"{gt.contract_id} has {len(gt.vulnerabilities)} vulnerabilities "
            f"(expected exactly 1 from folder-based labelling)"
        )
    print("[PASS] each contract has exactly one vulnerability label")


if __name__ == "__main__":
    tests = [
        test_returns_list_of_ground_truth,
        test_only_in_scope_classes,
        test_expected_counts,
        test_contract_paths_exist,
        test_contract_ids_unique,
        test_each_contract_has_one_vulnerability,
    ]

    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            print(f"[FAIL] {t.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"[ERROR] {t.__name__}: {exc}")
            failed += 1

    print()
    if failed:
        print(f"{failed}/{len(tests)} test(s) FAILED.")
        raise SystemExit(1)
    else:
        print(f"All {len(tests)}/{len(tests)} tests passed.")
