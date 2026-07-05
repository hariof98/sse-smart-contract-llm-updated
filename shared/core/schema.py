"""
Schema for vulnerabilities, predictions, and ground truth.

Every tool (Slither, Mythril, LLMs later) produces Prediction objects.
Every dataset is loaded into GroundTruth objects.
The scorer compares the two.

Keep this file small and stable — everything downstream depends on it.
"""

from dataclasses import dataclass, field
from typing import Optional


# Canonical vulnerability class names used throughout the pipeline.
# Tools report different names (Slither says "reentrancy-eth", Mythril uses
# SWC IDs). Each tool wrapper maps its native names to these.
VULNERABILITY_CLASSES = [
    "reentrancy",
    "access_control",
    "timestamp_dependency",
]


@dataclass
class Vulnerability:
    """A single vulnerability finding.

    Used for both ground truth labels and tool predictions.
    function and line are optional because some tools (and ground truth
    in some datasets) only report at contract level.
    """
    vuln_class: str                       # must be in VULNERABILITY_CLASSES
    function: Optional[str] = None        # function name if known
    line: Optional[int] = None            # line number if known


@dataclass
class GroundTruth:
    """What we know is actually wrong with a contract."""
    contract_id: str                      # unique identifier (e.g. filename)
    contract_path: str                    # path to the .sol file
    vulnerabilities: list[Vulnerability] = field(default_factory=list)


@dataclass
class Prediction:
    """What a tool says is wrong with a contract."""
    contract_id: str
    tool_name: str                        # "slither", "mythril", "gpt-4o", ...
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    runtime_seconds: float = 0.0
    tokens_used: Optional[int] = None     # only for LLMs
    raw_output: Optional[str] = None      # for debugging
