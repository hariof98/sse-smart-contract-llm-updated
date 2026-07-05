"""
Slither wrapper for the evaluation pipeline.

Runs Slither via subprocess, parses its JSON output, and returns a
Prediction object with vulnerability classes mapped to our canonical names.

Canonical mapping
-----------------
Slither detector name          → canonical class
----------------------------------------------
reentrancy-eth                 → reentrancy
reentrancy-no-eth              → reentrancy
reentrancy-benign              → reentrancy
reentrancy-events              → reentrancy
reentrancy-unlimited-gas       → reentrancy
suicidal                       → access_control
unprotected-upgrade            → access_control
controlled-delegatecall        → access_control
tx-origin                      → access_control
timestamp                      → timestamp_dependency

All other detector names are ignored (not in our evaluation scope).

Usage
-----
    from phases.phase0_traditional.tools.slither_tool import run
    prediction = run("/path/to/contract.sol")
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# When run directly Python puts the tool's dir on sys.path instead of the
# project root.  Fix that before importing siblings.
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import Prediction, Vulnerability, VULNERABILITY_CLASSES

TOOL_NAME = "slither"

# Extra directories to search for the slither binary when it is not on PATH.
# pip installs user-level scripts here on macOS when no venv is active.
# The first entry is the directory of the running Python interpreter — this
# ensures we find binaries installed in the same venv even when the venv is
# not activated (i.e. invoked via `venv/bin/python` directly).
_EXTRA_BIN_DIRS: list[Path] = [
    Path(sys.prefix) / "bin",
    Path.home() / "Library" / "Python" / "3.12" / "bin",
    Path.home() / "Library" / "Python" / "3.11" / "bin",
    Path.home() / "Library" / "Python" / "3.10" / "bin",
    Path("/usr/local/bin"),
    Path("/opt/homebrew/bin"),
]


def _slither_cmd() -> str:
    """Return 'slither' if it is on PATH, otherwise the first full path found."""
    import shutil
    if shutil.which("slither"):
        return "slither"
    for d in _EXTRA_BIN_DIRS:
        candidate = d / "slither"
        if candidate.is_file():
            return str(candidate)
    return "slither"  # will produce a clear FileNotFoundError at runtime


# solc-select stores each version's binary at:
#   ~/.solc-select/artifacts/solc-{version}/solc-{version}
_SOLC_ARTIFACTS = Path.home() / ".solc-select" / "artifacts"

# Pragma minor version  →  preferred installed solc version.
# The list is checked in order; the first installed version wins.
_PRAGMA_VERSION_MAP: list[tuple[str, list[str]]] = [
    # minor  candidate versions to try (in preference order)
    ("0.4",  ["0.4.25", "0.4.24", "0.4.23"]),
    ("0.5",  ["0.5.17", "0.5.16"]),
    ("0.6",  ["0.6.12", "0.6.11"]),
    ("0.7",  ["0.7.6",  "0.7.5"]),
    ("0.8",  ["0.8.20", "0.8.19"]),
]

_PRAGMA_RE = re.compile(r"pragma\s+solidity\s+([^;]+);")


def _detect_solc_binary(contract_path: Path) -> Optional[str]:
    """Return the path to the best matching installed solc binary, or None.

    Reads the first ``pragma solidity`` line in the file, derives the required
    minor version, then looks for a matching binary under solc-select's
    artifacts directory.  Returns None if no installed version satisfies the
    pragma (Slither will use whatever solc is on PATH).
    """
    try:
        text = contract_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    match = _PRAGMA_RE.search(text)
    if not match:
        return None

    spec = match.group(1).strip()  # e.g. "^0.4.19", ">=0.4.0 <0.6.0"

    for minor, candidates in _PRAGMA_VERSION_MAP:
        # Match if the spec mentions this minor version anywhere
        if minor in spec:
            for version in candidates:
                binary = _SOLC_ARTIFACTS / f"solc-{version}" / f"solc-{version}"
                if binary.is_file():
                    return str(binary)

    return None

# Slither detector slug  →  canonical vulnerability class.
# Only detectors mapped here are reported; all others are silently ignored.
DETECTOR_TO_CLASS: dict[str, str] = {
    # ── Reentrancy ────────────────────────────────────────────────────────
    "reentrancy-eth":           "reentrancy",
    "reentrancy-no-eth":        "reentrancy",
    "reentrancy-benign":        "reentrancy",
    "reentrancy-events":        "reentrancy",
    "reentrancy-unlimited-gas": "reentrancy",
    # ── Access control ────────────────────────────────────────────────────
    "suicidal":                 "access_control",
    "unprotected-upgrade":      "access_control",
    "controlled-delegatecall":  "access_control",
    "tx-origin":                "access_control",
    # ── Timestamp dependency ──────────────────────────────────────────────
    "timestamp":                "timestamp_dependency",
}

# Hard timeout per contract (seconds).
TIMEOUT_SECONDS: int = 60


def _map_detector(check: str) -> Optional[str]:
    """Return the canonical class for a Slither detector name, or None."""
    return DETECTOR_TO_CLASS.get(check)


def _parse_detectors(slither_json: dict) -> list[Vulnerability]:
    """Extract Vulnerability objects from a parsed Slither JSON result.

    Each detector hit that maps to a canonical class becomes one
    Vulnerability.  Duplicate classes within one contract are deduplicated
    so we emit at most one Vulnerability per canonical class (matching the
    class-only scoring criterion).
    """
    detectors = (
        slither_json.get("results", {}).get("detectors", [])
    )

    seen_classes: set[str] = set()
    vulns: list[Vulnerability] = []

    for det in detectors:
        check: str = det.get("check", "")
        vuln_class = _map_detector(check)
        if vuln_class is None or vuln_class in seen_classes:
            continue

        # Best-effort: pull function name and first line from the first element.
        function_name: Optional[str] = None
        line_number: Optional[int] = None
        elements: list[dict] = det.get("elements", [])
        if elements:
            first = elements[0]
            # Function name: present when the element is a function, or when
            # a node element's parent is a function.
            tsf = first.get("type_specific_fields", {})
            parent = tsf.get("parent", {})
            if first.get("type") == "function":
                function_name = first.get("name")
            elif parent.get("type") == "function":
                function_name = parent.get("name")

            lines: list[int] = (
                first.get("source_mapping", {}).get("lines", [])
            )
            if lines:
                line_number = lines[0]

        seen_classes.add(vuln_class)
        vulns.append(
            Vulnerability(
                vuln_class=vuln_class,
                function=function_name,
                line=line_number,
            )
        )

    return vulns


def run(contract_path: str) -> Prediction:
    """Run Slither on *contract_path* and return a Prediction.

    Parameters
    ----------
    contract_path:
        Absolute or relative path to a .sol file.

    Returns
    -------
    Prediction
        Always returns a Prediction (never raises).  On timeout or any
        subprocess error the vulnerabilities list is empty and the error
        message is stored in ``raw_output``.
    """
    path = Path(contract_path)
    contract_id = path.name

    start = time.monotonic()

    # Pick the right solc binary for this contract's pragma.
    solc_binary = _detect_solc_binary(path)

    cmd = [
        _slither_cmd(),
        str(path),
        "--json", "-",          # emit JSON to stdout
        "--disable-color",      # no ANSI codes in output
    ]
    if solc_binary:
        cmd += ["--solc", solc_binary]

    raw_output: Optional[str] = None
    vulns: list[Vulnerability] = []

    # Build a subprocess environment that includes the directories where
    # pip installs user-level scripts (slither, solc, solc-select).
    # Without this, Slither can't find the `solc` compiler and exits silently.
    env = os.environ.copy()
    extra_paths = [str(d) for d in _EXTRA_BIN_DIRS if d.is_dir()]
    if extra_paths:
        env["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + env.get("PATH", "")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env=env,
        )
        # Slither writes JSON to stdout regardless of exit code.
        # Exit code 1 means findings were found; 0 means none.
        # Other non-zero exit codes indicate a hard error.
        raw_output = result.stdout or result.stderr

        if result.stdout.strip():
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raw_output = f"JSON parse error: {exc}\n\nstdout:\n{result.stdout}"
                data = {}

            if data.get("success", False):
                vulns = _parse_detectors(data)
            else:
                error_msg = data.get("error") or result.stderr or "unknown error"
                raw_output = f"Slither reported failure: {error_msg}\n\nraw:\n{result.stdout}"
        else:
            # No stdout — compilation probably failed; stderr has the reason.
            raw_output = f"No JSON output.\nstderr:\n{result.stderr}"

    except subprocess.TimeoutExpired:
        raw_output = f"Timed out after {TIMEOUT_SECONDS}s"
    except FileNotFoundError:
        raw_output = (
            "slither executable not found. "
            "Install it with:  pip install slither-analyzer"
        )
    except Exception as exc:  # noqa: BLE001
        raw_output = f"Unexpected error: {exc}"

    elapsed = time.monotonic() - start

    return Prediction(
        contract_id=contract_id,
        tool_name=TOOL_NAME,
        vulnerabilities=vulns,
        runtime_seconds=round(elapsed, 3),
        raw_output=raw_output,
    )


# ---------------------------------------------------------------------------
# Standalone smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        # Use the first reentrancy contract from the bundled dataset.
        dataset = (
            _project_root
            / "shared" / "datasets" / "smartbugs-curated" / "dataset"
            / "reentrancy"
        )
        candidates = sorted(dataset.glob("*.sol"))
        if not candidates:
            print("No .sol file found for smoke-test. Pass a path as argument.")
            sys.exit(1)
        contract = str(candidates[0])
    else:
        contract = sys.argv[1]

    print(f"Running Slither on: {contract}")
    pred = run(contract)
    print(f"  tool        : {pred.tool_name}")
    print(f"  contract_id : {pred.contract_id}")
    print(f"  runtime     : {pred.runtime_seconds}s")
    print(f"  findings    : {len(pred.vulnerabilities)}")
    for v in pred.vulnerabilities:
        print(f"    - {v.vuln_class}  fn={v.function}  line={v.line}")
    if not pred.vulnerabilities:
        print(f"  raw_output  : {(pred.raw_output or '')[:300]}")
