"""
Mythril wrapper for the evaluation pipeline.

Runs Mythril via Docker (mythril/myth image), parses its JSON output, and
returns a Prediction object with vulnerability classes mapped to our
canonical names.

Canonical mapping
-----------------
SWC ID   Title                             → canonical class
------------------------------------------------------------------
SWC-107  Reentrancy                        → reentrancy
SWC-105  Unprotected Ether Withdrawal      → access_control
SWC-106  Unprotected SELFDESTRUCT          → access_control
SWC-112  Delegatecall to Untrusted Callee  → access_control
SWC-115  Authorization through tx.origin   → access_control
SWC-116  Block values / Timestamp Dep.     → timestamp_dependency

All other SWC IDs are ignored (not in our evaluation scope).

Prerequisites
-------------
    docker pull mythril/myth

Usage
-----
    from phases.phase0_traditional.tools.mythril_tool import run
    prediction = run("/path/to/contract.sol")
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Allow running directly: python3 phases/phase0_traditional/tools/mythril_tool.py
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import Prediction, Vulnerability, VULNERABILITY_CLASSES

TOOL_NAME = "mythril"

# SWC ID (as string, no leading zeros) → canonical vulnerability class.
SWC_TO_CLASS: dict[str, str] = {
    # ── Reentrancy ─────────────────────────────────────────────────────
    "107": "reentrancy",
    # ── Access control ─────────────────────────────────────────────────
    "105": "access_control",    # Unprotected Ether Withdrawal
    "106": "access_control",    # Unprotected SELFDESTRUCT
    "112": "access_control",    # Delegatecall to Untrusted Callee
    "115": "access_control",    # Authorization through tx.origin
    # ── Timestamp dependency ────────────────────────────────────────────
    "116": "timestamp_dependency",
}

# Mythril symbolic-execution budget per contract (seconds).
# Increase for better recall at the cost of longer runtime.
EXECUTION_TIMEOUT: int = 60

# Hard subprocess timeout — must be > EXECUTION_TIMEOUT to allow for
# Docker startup and shutdown overhead.
SUBPROCESS_TIMEOUT: int = EXECUTION_TIMEOUT + 60   # 120 s

# ── Solidity version detection ────────────────────────────────────────────
# Mythril's Docker image ships with a single solc version (typically 0.8.x).
# SmartBugs contracts mostly need 0.4.x.  We parse the pragma and pass
# --solv <version> so Mythril downloads the right compiler inside the
# container.
_PRAGMA_RE = re.compile(r"pragma\s+solidity\s+([^;]+);")

# Pragma minor version → preferred solc version to request via --solv.
_PRAGMA_SOLV_MAP: list[tuple[str, str]] = [
    ("0.4", "0.4.25"),
    ("0.5", "0.5.17"),
    ("0.6", "0.6.12"),
    ("0.7", "0.7.6"),
    ("0.8", "0.8.20"),
]


def _detect_solv(contract_path: Path) -> Optional[str]:
    """Return the solc version string for --solv, or None to use the default."""
    try:
        text = contract_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    match = _PRAGMA_RE.search(text)
    if not match:
        return None

    spec = match.group(1).strip()  # e.g. "^0.4.19"
    for minor, version in _PRAGMA_SOLV_MAP:
        if minor in spec:
            return version
    return None


def _map_swc(swc_id: str) -> Optional[str]:
    """Return canonical class for a SWC ID string, or None to skip."""
    # Normalise: strip leading zeros, then look up
    return SWC_TO_CLASS.get(swc_id.lstrip("0") or "0")


def _parse_issues(mythril_json: dict) -> list[Vulnerability]:
    """Extract Vulnerability objects from parsed Mythril JSON output.

    Deduplicated by canonical class (class-only matching criterion).
    """
    issues: list[dict] = mythril_json.get("issues", [])

    seen_classes: set[str] = set()
    vulns: list[Vulnerability] = []

    for issue in issues:
        swc_raw: str = str(issue.get("swc-id", ""))
        vuln_class = _map_swc(swc_raw)
        if vuln_class is None or vuln_class in seen_classes:
            continue

        line_number: Optional[int] = issue.get("lineno")

        seen_classes.add(vuln_class)
        vulns.append(
            Vulnerability(
                vuln_class=vuln_class,
                function=None,      # Mythril does not report function names
                line=line_number,
            )
        )

    return vulns


def run(contract_path: str) -> Prediction:
    """Run Mythril on *contract_path* via Docker and return a Prediction.

    Parameters
    ----------
    contract_path:
        Absolute or relative path to a .sol file.

    Returns
    -------
    Prediction
        Always returns a Prediction (never raises).  On timeout, Docker
        error, or any other failure the vulnerabilities list is empty and
        the error is stored in ``raw_output``.
    """
    path = Path(contract_path).resolve()
    contract_id = path.name

    start = time.monotonic()

    # Mount the contract's parent directory as /mnt inside the container.
    # Mythril analyzes /mnt/<filename>.
    mount_src = str(path.parent)
    container_path = f"/mnt/{path.name}"

    # Detect the required solc version from the contract's pragma.
    solv = _detect_solv(path)

    cmd = [
        "docker", "run", "--rm",
        "--dns", "8.8.8.8",
        "-v", f"{mount_src}:/mnt",
        "mythril-patched",
        "analyze", container_path,
        "-o", "json",
        "--execution-timeout", str(EXECUTION_TIMEOUT),
        "--solver-timeout", "10000",    # Z3 solver budget (ms)
    ]
    if solv:
        cmd += ["--solv", solv]

    raw_output: Optional[str] = None
    vulns: list[Vulnerability] = []

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        # Mythril exit codes:
        #   0  →  analysis completed, no issues
        #   1  →  analysis completed, issues found  (or hard error)
        # The only reliable signal is the stdout content.
        combined = result.stdout.strip()
        raw_output = combined or result.stderr

        if not combined:
            raw_output = f"No output from Mythril.\nstderr:\n{result.stderr}"
        elif combined.startswith("{"):
            # JSON output
            try:
                data = json.loads(combined)
            except json.JSONDecodeError as exc:
                raw_output = f"JSON parse error: {exc}\n\nstdout:\n{combined}"
                data = {}

            if data.get("success", False):
                vulns = _parse_issues(data)
            else:
                err = data.get("error") or result.stderr or "unknown"
                raw_output = f"Mythril reported failure: {err}\n\nraw:\n{combined}"
        else:
            # Mythril sometimes emits a plain-text "No issues found." message
            # when -o json yields no issues in some versions.
            if "no issues" in combined.lower():
                vulns = []
                raw_output = combined
            else:
                raw_output = f"Unexpected non-JSON output:\n{combined}"

    except subprocess.TimeoutExpired:
        raw_output = (
            f"Timed out after {SUBPROCESS_TIMEOUT}s "
            f"(execution-timeout={EXECUTION_TIMEOUT}s)"
        )
    except FileNotFoundError:
        raw_output = (
            "docker executable not found.\n"
            "Install Docker Desktop and pull the image with:\n"
            "  docker pull mythril/myth"
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
    if len(sys.argv) < 2:
        dataset = (
            _project_root
            / "shared" / "datasets" / "smartbugs-curated" / "dataset" / "reentrancy"
        )
        candidates = sorted(dataset.glob("*.sol"))
        if not candidates:
            print("No .sol file found. Pass a path as argument.")
            sys.exit(1)
        contract = str(candidates[0])
    else:
        contract = sys.argv[1]

    print(f"Running Mythril on: {contract}")
    print(f"  execution-timeout : {EXECUTION_TIMEOUT}s")
    print(f"  subprocess-timeout: {SUBPROCESS_TIMEOUT}s")
    print()
    pred = run(contract)
    print(f"  tool        : {pred.tool_name}")
    print(f"  contract_id : {pred.contract_id}")
    print(f"  runtime     : {pred.runtime_seconds}s")
    print(f"  findings    : {len(pred.vulnerabilities)}")
    for v in pred.vulnerabilities:
        print(f"    - {v.vuln_class}  line={v.line}")
    if not pred.vulnerabilities:
        print(f"  raw_output  : {(pred.raw_output or '')[:400]}")
