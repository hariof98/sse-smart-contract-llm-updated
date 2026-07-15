"""
Hybrid filter prompt (Phase 4).

The LLM acts as a FILTER over Slither's output: it reviews each in-scope Slither
finding and marks it CONFIRMED or REJECTED. This is a filter-only design — the
LLM must NOT add findings Slither did not report (no augmentation). The final
prediction keeps only the CONFIRMED findings.

Prompts are experimental variables and are intentionally FIXED. Do not tune them
mid-experiment.
"""

import json

STRATEGY_NAME = "filter_review"

SYSTEM_PROMPT = """You are a smart contract security auditor. A static-analysis tool (Slither) has already scanned a Solidity contract and produced a list of candidate findings. Static analysers are precise but noisy — they raise false positives.

Your job is to REVIEW each Slither finding against the actual contract code and decide whether it is real.

Only these three vulnerability classes are in scope:
- "reentrancy": an external call is made before the contract updates its own state.
- "access_control": a sensitive action is callable by an unauthorised party (missing/incorrect access checks).
- "timestamp_dependency": block.timestamp / block.number / blockhash drives a security-critical decision.

Rules (strict):
- For EACH finding given to you, output a decision: "confirmed" (the vulnerability is genuinely present) or "rejected" (it is a false positive).
- You MUST NOT add any finding that is not in the provided list. This is a filter, not a new analysis. Do not introduce new classes, functions, or issues.
- Copy each finding's object verbatim into "original_finding".
- Give a short (one or two sentence) reasoning per finding.

Output ONLY a single JSON object, with no text before or after it, in exactly this form:
{"reviewed": [{"original_finding": {"vuln_class": "..."}, "decision": "confirmed", "reasoning": "..."}]}

If the provided list is empty, return:
{"reviewed": []}"""


def build_messages(contract_source: str, slither_findings: list[dict]) -> list[dict]:
    """Return the chat messages for the hybrid filter call.

    Parameters
    ----------
    contract_source:
        Full text of the .sol file under review.
    slither_findings:
        Slither's in-scope findings, one dict each (verbatim), e.g.
        ``[{"vuln_class": "reentrancy"}, {"vuln_class": "timestamp_dependency"}]``.

    Returns
    -------
    list[dict]
        ``messages`` ready to pass to the shared chat client.
    """
    findings_json = json.dumps(slither_findings, ensure_ascii=False, indent=2)

    user_content = (
        "Review the static-analysis findings below against the contract code. "
        "Confirm the real ones, reject the false positives. Do NOT add any finding "
        "that is not in the list.\n\n"
        "=== CONTRACT SOURCE ===\n"
        f"{contract_source}\n\n"
        "=== SLITHER FINDINGS (in-scope, review each) ===\n"
        f"{findings_json}\n\n"
        "=== YOUR TASK ===\n"
        "For each finding above, decide 'confirmed' or 'rejected' with a short "
        "reasoning. Return only the JSON object."
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
