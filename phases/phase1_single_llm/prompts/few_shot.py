"""
Few-shot prompt strategy.

Three hand-crafted synthetic examples are included before the target
contract.  Each example demonstrates one of the three canonical
vulnerability classes.

The examples are NOT drawn from the SmartBugs Curated test set.
"""

SYSTEM_PROMPT = """You are an expert smart contract security auditor specializing in Solidity vulnerability detection.

Analyze the provided Solidity smart contract and identify which of the following vulnerability classes are present:
- "reentrancy"           : The contract makes an external call before updating its own state, allowing re-entrant calls.
- "access_control"       : Critical functions (e.g. selfdestruct, fund withdrawal, ownership changes) are callable by unauthorized parties.
- "timestamp_dependency" : The contract uses block.timestamp (or block.number) to make security-critical decisions.

Rules:
1. Only report classes from the list above. Do not invent new class names.
2. Report a class only if you are confident it is genuinely present.
3. Return ONLY a valid JSON object — no explanation, no markdown, no extra text.

Output format:
{"vulnerabilities": ["class1", "class2"]}

If no vulnerabilities from the list are found, return:
{"vulnerabilities": []}"""

# ── Synthetic few-shot examples (hand-crafted, not from test set) ──────────

_EXAMPLE_REENTRANCY_CONTRACT = """\
pragma solidity ^0.8.0;
contract Bank {
    mapping(address => uint256) public balances;

    function deposit() public payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw(uint256 amount) public {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        // External call is made BEFORE state is updated — reentrancy risk
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
        balances[msg.sender] -= amount;  // state updated too late
    }
}"""

_EXAMPLE_ACCESS_CONTROL_CONTRACT = """\
pragma solidity ^0.8.0;
contract Vault {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    // No access control — any caller can destroy the contract
    function close() public {
        selfdestruct(payable(msg.sender));
    }
}"""

_EXAMPLE_TIMESTAMP_CONTRACT = """\
pragma solidity ^0.8.0;
contract Lottery {
    address[] public players;

    function enter() public payable {
        players.push(msg.sender);
    }

    function pickWinner() public {
        // block.timestamp can be manipulated by miners — insecure randomness
        uint index = block.timestamp % players.length;
        payable(players[index]).transfer(address(this).balance);
        players = new address[](0);
    }
}"""


def build_messages(contract_source: str) -> list[dict]:
    """Return the messages list for the few-shot strategy.

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

        # Example 1 — reentrancy
        {"role": "user", "content": f"Analyze this Solidity contract:\n\n{_EXAMPLE_REENTRANCY_CONTRACT}"},
        {"role": "assistant", "content": '{"vulnerabilities": ["reentrancy"]}'},

        # Example 2 — access_control
        {"role": "user", "content": f"Analyze this Solidity contract:\n\n{_EXAMPLE_ACCESS_CONTROL_CONTRACT}"},
        {"role": "assistant", "content": '{"vulnerabilities": ["access_control"]}'},

        # Example 3 — timestamp_dependency
        {"role": "user", "content": f"Analyze this Solidity contract:\n\n{_EXAMPLE_TIMESTAMP_CONTRACT}"},
        {"role": "assistant", "content": '{"vulnerabilities": ["timestamp_dependency"]}'},

        # Target contract
        {"role": "user", "content": f"Analyze this Solidity contract:\n\n{contract_source}"},
    ]


STRATEGY_NAME = "few_shot"
