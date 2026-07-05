"""
Quick demo of the schema. Run with: python examples/demo_schema.py

Shows what ground truth and a tool prediction look like in code.
This is not a test — it's a sanity check that the data shapes feel right.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import Vulnerability, GroundTruth, Prediction


# Ground truth for one contract from SmartBugs
ground_truth = GroundTruth(
    contract_id="reentrance_1",
    contract_path="datasets/smartbugs/reentrancy/reentrance_1.sol",
    vulnerabilities=[
        Vulnerability(vuln_class="reentrancy", function="withdrawBalance", line=23),
    ],
)

# What Slither might predict for the same contract
slither_prediction = Prediction(
    contract_id="reentrance_1",
    tool_name="slither",
    vulnerabilities=[
        Vulnerability(vuln_class="reentrancy", function="withdrawBalance", line=23),
        # False positive — Slither sometimes flags timestamp use that isn't a real bug
        Vulnerability(vuln_class="timestamp_dependency", function="getNow", line=45),
    ],
    runtime_seconds=2.4,
)

print("Ground truth:")
print(f"  {ground_truth.contract_id}: {[v.vuln_class for v in ground_truth.vulnerabilities]}")
print()
print("Slither prediction:")
print(f"  {slither_prediction.contract_id}: {[v.vuln_class for v in slither_prediction.vulnerabilities]}")
print(f"  runtime: {slither_prediction.runtime_seconds}s")
