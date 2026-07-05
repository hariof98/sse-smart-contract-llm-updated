"""
Moderator prompt (Phase 3).

The moderator runs sequentially AFTER the three specialists finish. It sees
the contract source plus every specialist's raw JSON output and produces the
final vulnerability list that gets scored.

It may drop findings it judges to be false positives, merge duplicates, and
add a finding no specialist reported — but only when the code strongly
justifies it. Uses the SAME model as the specialists in a given run.

Prompts are experimental variables and are intentionally FIXED.
"""

STRATEGY_NAME = "moderator"

SYSTEM_PROMPT = """You are the lead security auditor. Three specialist auditors have each reviewed the same Solidity contract, one vulnerability class each: reentrancy, access_control, timestamp_dependency. You are given the contract source and each specialist's JSON findings.

Produce the FINAL vulnerability list for this contract. Only these three classes are in scope: reentrancy, access_control, timestamp_dependency.

You may:
- DROP a specialist finding you judge to be a false positive — verify it against the actual code, do not rubber-stamp.
- MERGE duplicate findings that refer to the same underlying issue.
- ADD a class no specialist reported, but ONLY if the contract code strongly justifies it.

Report a class only if it is genuinely present in this contract.

Output ONLY a single JSON object, with no text before or after it, in exactly this form:
{"findings": [{"vuln_class": "...", "function": "<name or null>", "line": <int or null>, "reasoning": "<one or two sentences>"}]}

If, after review, no class is genuinely present:
{"findings": []}"""


def build_messages(contract_source: str, specialist_outputs: list[dict]) -> list[dict]:
    """Return the chat messages for the moderator call.

    Parameters
    ----------
    contract_source:
        Full text of the .sol file under review.
    specialist_outputs:
        One dict per specialist, each with:
          ``specialist`` — the specialist's assigned class name,
          ``response``   — the specialist's raw response text (verbatim),
                           or a short note if that specialist call failed.

    Returns
    -------
    list[dict]
        ``messages`` ready to pass to the shared chat client.
    """
    blocks: list[str] = []
    for out in specialist_outputs:
        name = out.get("specialist", "unknown")
        response = out.get("response") or "(no output — this specialist call failed)"
        blocks.append(
            f"--- {name} specialist ---\n{response}"
        )
    specialists_block = "\n\n".join(blocks) if blocks else "(no specialist output available)"

    user_content = (
        "Aggregate and arbitrate the specialist findings for this Solidity contract.\n\n"
        "=== CONTRACT SOURCE ===\n"
        f"{contract_source}\n\n"
        "=== SPECIALIST FINDINGS (verbatim) ===\n"
        f"{specialists_block}\n\n"
        "=== YOUR TASK ===\n"
        "Review the specialist findings against the contract code. Drop false positives, "
        "merge duplicates, add a strongly-justified class if a specialist missed it, and "
        "return the final list of genuinely-present vulnerability classes."
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
