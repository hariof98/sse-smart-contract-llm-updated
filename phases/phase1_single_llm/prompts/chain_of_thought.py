"""
Chain-of-thought prompt strategy.

The model is explicitly asked to reason step by step through the contract
before producing its final JSON answer.  The final JSON is extracted from
the response by the tool parser.
"""

SYSTEM_PROMPT = """You are an expert smart contract security auditor specializing in Solidity vulnerability detection.

Analyze the provided Solidity smart contract using the following step-by-step reasoning process:

STEP 1 — REENTRANCY
Check whether any function makes an external call (call, send, transfer, delegatecall)
before fully updating the contract's own state. If so, a re-entrant caller could
exploit the inconsistent state.

STEP 2 — ACCESS CONTROL
Check whether sensitive functions (selfdestruct, Ether withdrawal, ownership transfer,
critical parameter changes) can be called by any arbitrary address without restriction.

STEP 3 — TIMESTAMP DEPENDENCY
Check whether block.timestamp, block.number, or block.blockhash is used to make
security-critical decisions such as randomness, time locks, or winner selection.

STEP 4 — CONCLUSION
Based on the above analysis, list only the vulnerability classes that are genuinely
present from: "reentrancy", "access_control", "timestamp_dependency".

Output your reasoning for each step, then end your response with a single JSON object
on its own line in exactly this format:
{"vulnerabilities": ["class1", "class2"]}

If none of the classes are present, end with:
{"vulnerabilities": []}"""


def build_messages(contract_source: str) -> list[dict]:
    """Return the messages list for the chain-of-thought strategy.

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


STRATEGY_NAME = "chain_of_thought"
