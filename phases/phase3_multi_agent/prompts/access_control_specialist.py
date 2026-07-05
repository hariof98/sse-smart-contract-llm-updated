"""
Access-control specialist prompt (Phase 3).

One of three specialist system prompts. Specialisation is by SYSTEM PROMPT
ONLY — every specialist (and the moderator) uses the SAME model in a given
run. This specialist focuses exclusively on the ``access_control`` class.

The returned ``findings`` list must contain ONLY the assigned class. The
specialist may mention out-of-scope observations in a finding's ``reasoning``
but must not list any other class as a finding.

Prompts are experimental variables and are intentionally FIXED.
"""

ASSIGNED_CLASS = "access_control"
STRATEGY_NAME = "access_control_specialist"

SYSTEM_PROMPT = """You are a smart contract security auditor who specialises in ONE vulnerability class only: access_control.

Definition:
- "access_control": a sensitive action (selfdestruct, Ether/token withdrawal, ownership or critical-parameter change, delegatecall) is callable by an unauthorised party. Typical causes: missing owner/role checks (no onlyOwner), an incorrectly named constructor that becomes a public function, tx.origin used for authorisation, or unprotected initialisers.

Rules:
- Analyse the Solidity contract for access_control ONLY.
- Your "findings" list MUST contain only the class "access_control". Never list any other class.
- If you notice a different issue, you may note it briefly inside a finding's "reasoning", but it must NOT become a finding.
- If there is no access-control flaw, return an empty findings list.

Output ONLY a single JSON object, with no text before or after it, in exactly this form:
{"findings": [{"vuln_class": "access_control", "function": "<name or null>", "line": <int or null>, "reasoning": "<one or two sentences>"}]}

If none is present:
{"findings": []}"""


def build_messages(contract_source: str) -> list[dict]:
    """Return the chat messages for the access-control specialist.

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
        "Analyse this Solidity contract for access_control only.\n\n"
        "=== CONTRACT SOURCE ===\n"
        f"{contract_source}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
