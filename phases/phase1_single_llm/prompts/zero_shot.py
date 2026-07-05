"""
Zero-shot prompt strategy.

The contract is sent directly with no examples.
The model must identify vulnerabilities from the contract text alone.
"""

SYSTEM_PROMPT = """You are an expert smart contract security auditor specializing in Solidity vulnerability detection.

Analyze the provided Solidity smart contract and identify which of the following vulnerability classes are present:
- "reentrancy"       : The contract makes an external call before updating its own state, allowing re-entrant calls.
- "access_control"   : Critical functions (e.g. selfdestruct, fund withdrawal, ownership changes) are callable by unauthorized parties.
- "timestamp_dependency" : The contract uses block.timestamp (or block.number) to make security-critical decisions.

Rules:
1. Only report classes from the list above. Do not invent new class names.
2. Report a class only if you are confident it is genuinely present.
3. Return ONLY a valid JSON object — no explanation, no markdown, no extra text.

Output format:
{"vulnerabilities": ["class1", "class2"]}

If no vulnerabilities from the list are found, return:
{"vulnerabilities": []}"""


def build_messages(contract_source: str) -> list[dict]:
    """Return the messages list for the zero-shot strategy.

    Parameters
    ----------
    contract_source:
        Full text of the .sol file.

    Returns
    -------
    list[dict]
        Ready to pass as the ``messages`` argument to the OpenAI client.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Analyze this Solidity contract:\n\n{contract_source}"},
    ]


STRATEGY_NAME = "zero_shot"
