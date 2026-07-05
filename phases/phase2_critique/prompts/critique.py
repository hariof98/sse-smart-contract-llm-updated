"""
Critique prompt strategy (Phase 2).

This is the prompt used by the CRITIC model in the two-agent
detector -> critic pipeline.  The critic sees three things:

    1. The full Solidity contract source.
    2. The detector model's list of detected vulnerability classes.
    3. The detector model's full reasoning.

It is asked to independently review that analysis and return a corrected
final list of vulnerability classes.

IMPORTANT — this prompt is an experimental variable and is intentionally
FIXED.  Do not tune it during an experiment run; if you want to study prompt
sensitivity, do it as a separate, clearly-labelled ablation with one model
pair (see docs/PHASE2.md).
"""

SYSTEM_PROMPT = """You are a senior smart contract security auditor performing an independent SECOND-OPINION review of another auditor's vulnerability analysis of a Solidity contract.

You will be given:
1. The Solidity contract source code.
2. The prior auditor's reported vulnerability classes.
3. The prior auditor's full reasoning.

Your task is to critically review that analysis for ONLY these three classes:
- "reentrancy"           : an external call (call, send, transfer, delegatecall) is made before the contract updates its own state.
- "access_control"       : a sensitive action (selfdestruct, Ether withdrawal, ownership/critical-parameter change, delegatecall) is callable by an unauthorized party.
- "timestamp_dependency" : block.timestamp / block.number / block.blockhash drives a security-critical decision.

Review guidelines:
- Do NOT rubber-stamp the prior analysis. Independently verify every claim against the actual contract code.
- Remove FALSE POSITIVES: classes the prior auditor reported that are not genuinely present.
- Add MISSED vulnerabilities: classes that are genuinely present but the prior auditor did not report.
- Be alert to confident-but-incorrect reasoning. A convincing explanation does not make a vulnerability real — check the code yourself.
- Report a class only if it is genuinely present in this contract.

First briefly explain your review of each reported and each missing class, then end your
response with a single JSON object on its own line in exactly this format:
{"vulnerabilities": ["class1", "class2"]}

If, after review, no classes are genuinely present, end with:
{"vulnerabilities": []}"""


def build_messages(
    contract_source: str,
    detector_vulnerabilities: list[str],
    detector_reasoning: str,
) -> list[dict]:
    """Return the messages list for the critic call.

    Parameters
    ----------
    contract_source:
        Full text of the .sol file under review.
    detector_vulnerabilities:
        The detector model's reported vulnerability classes.
    detector_reasoning:
        The detector model's full response/reasoning text.

    Returns
    -------
    list[dict]
        Ready to pass as the ``messages`` argument to the chat client.
    """
    reported = ", ".join(detector_vulnerabilities) if detector_vulnerabilities else "(none)"

    user_content = (
        "Analyze and review the prior vulnerability analysis of this Solidity contract.\n\n"
        "=== CONTRACT SOURCE ===\n"
        f"{contract_source}\n\n"
        "=== PRIOR ANALYSIS (from another model) ===\n"
        f"Reported vulnerability classes: {reported}\n\n"
        "Reasoning:\n"
        f"{detector_reasoning}\n\n"
        "=== YOUR TASK ===\n"
        "Independently review the analysis above. Correct any false positives, add any "
        "missed vulnerabilities, and provide your final list of genuinely-present "
        "vulnerability classes."
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]


STRATEGY_NAME = "critique"
