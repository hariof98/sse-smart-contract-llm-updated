"""
Reentrancy specialist prompt (Phase 3).

One of three specialist system prompts. Specialisation is by SYSTEM PROMPT
ONLY — every specialist (and the moderator) uses the SAME model in a given
run. This specialist focuses exclusively on the ``reentrancy`` class.

The returned ``findings`` list must contain ONLY the assigned class. The
specialist may mention out-of-scope observations in a finding's ``reasoning``
but must not list any other class as a finding.

Prompts are experimental variables and are intentionally FIXED. Do not tune
them mid-experiment; run prompt-sensitivity studies as labelled ablations.
"""

ASSIGNED_CLASS = "reentrancy"
STRATEGY_NAME = "reentrancy_specialist"

SYSTEM_PROMPT = """You are a smart contract security auditor who specialises in ONE vulnerability class only: reentrancy.

Definition:
- "reentrancy": the contract makes an external call (call/send/transfer/delegatecall) BEFORE it updates its own state, so the callee can re-enter the function and repeat the action (e.g. withdraw multiple times).

Rules:
- Analyse the Solidity contract for reentrancy ONLY.
- Your "findings" list MUST contain only the class "reentrancy". Never list any other class.
- If you notice a different issue, you may note it briefly inside a finding's "reasoning", but it must NOT become a finding.
- If there is no reentrancy, return an empty findings list.

Output ONLY a single JSON object, with no text before or after it, in exactly this form:
{"findings": [{"vuln_class": "reentrancy", "function": "<name or null>", "line": <int or null>, "reasoning": "<one or two sentences>"}]}

If none is present:
{"findings": []}"""


def build_messages(contract_source: str) -> list[dict]:
    """Return the chat messages for the reentrancy specialist.

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
        "Analyse this Solidity contract for reentrancy only.\n\n"
        "=== CONTRACT SOURCE ===\n"
        f"{contract_source}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
