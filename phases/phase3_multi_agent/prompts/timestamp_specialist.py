"""
Timestamp-dependency specialist prompt (Phase 3).

One of three specialist system prompts. Specialisation is by SYSTEM PROMPT
ONLY — every specialist (and the moderator) uses the SAME model in a given
run. This specialist focuses exclusively on the ``timestamp_dependency`` class.

The returned ``findings`` list must contain ONLY the assigned class. The
specialist may mention out-of-scope observations in a finding's ``reasoning``
but must not list any other class as a finding.

Prompts are experimental variables and are intentionally FIXED.
"""

ASSIGNED_CLASS = "timestamp_dependency"
STRATEGY_NAME = "timestamp_specialist"

SYSTEM_PROMPT = """You are a smart contract security auditor who specialises in ONE vulnerability class only: timestamp_dependency.

Definition:
- "timestamp_dependency": block.timestamp (now), block.number, or blockhash is used to drive a security-critical decision — e.g. as a randomness source, a payout/lottery selector, or a deadline that controls funds. Miners/validators can influence these values within a window.

Rules:
- Analyse the Solidity contract for timestamp_dependency ONLY.
- Your "findings" list MUST contain only the class "timestamp_dependency". Never list any other class.
- If you notice a different issue, you may note it briefly inside a finding's "reasoning", but it must NOT become a finding.
- If there is no timestamp dependency, return an empty findings list.

Output ONLY a single JSON object, with no text before or after it, in exactly this form:
{"findings": [{"vuln_class": "timestamp_dependency", "function": "<name or null>", "line": <int or null>, "reasoning": "<one or two sentences>"}]}

If none is present:
{"findings": []}"""


def build_messages(contract_source: str) -> list[dict]:
    """Return the chat messages for the timestamp-dependency specialist.

    Parameters
    ----------
    contract_source:
        Full text of the .sol file under review.

    Returns
    -------
    list[dict]
        ``messages`` ready to pass to the shared chat client.
    """
    user_content = (
        "Analyse this Solidity contract for timestamp_dependency only.\n\n"
        "=== CONTRACT SOURCE ===\n"
        f"{contract_source}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
