"""
Two-agent critique tool (Phase 2).

A single pluggable tool that wraps TWO different LLMs in a one-round
detector -> critic pipeline:

    contract -> Detector LLM -> (classes + reasoning) -> Critic LLM -> final classes

From the evaluation pipeline's point of view this is still just one tool with
one ``run(contract_path) -> Prediction`` function, so the scorer, runner, and
core logger are completely unchanged (this is exactly the plug-in contract
established in Phase 0).

The critic is a DIFFERENT model from the detector (cross-model critique).  It
sees the contract, the detector's reported classes, and the detector's full
reasoning, then returns a revised list.  The revised list is the final
prediction that gets scored.

Research question (RQ4): does adding a critique step justify its extra cost?
To answer that, this tool records a full cost + behaviour breakdown per
contract in ``raw_output`` (detector vs critic tokens, what the critic
removed/added/kept).  The Phase 2 logger turns that into cost-adjusted
metrics.

Usage
-----
    from phases.phase2_critique.tools.llm_critique import make_tool
    tool_fn = make_tool(detector="gpt-4o-mini", critic="gpt-4o")
    prediction = tool_fn("/path/to/contract.sol")
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

# Allow running directly: python3 phases/phase2_critique/tools/llm_critique.py
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import Prediction, Vulnerability
from phases.phase2_critique.prompts import critique as critique_prompt
from phases.phase1_single_llm.tools.llm_single_agent import (
    SUPPORTED_MODELS,
    VALID_STRATEGIES,
    call_chat,
    parse_vulnerabilities,
    run as single_agent_run,
)

# Default detector strategy.  chain_of_thought is required here: the critic
# needs the detector's reasoning to review, so the detector must produce it.
DEFAULT_STRATEGY = "chain_of_thought"


def _detector_reasoning(detector_pred: Prediction) -> str:
    """Pull the detector's full response text out of its raw_output JSON."""
    if not detector_pred.raw_output:
        return ""
    try:
        meta = json.loads(detector_pred.raw_output)
    except (json.JSONDecodeError, TypeError):
        return ""
    return meta.get("response", "") or ""


def _detector_tokens(detector_pred: Prediction) -> tuple[int, int, int, Optional[str]]:
    """Return (prompt, completion, total, error) tokens from a detector Prediction."""
    if not detector_pred.raw_output:
        return 0, 0, 0, None
    try:
        meta = json.loads(detector_pred.raw_output)
    except (json.JSONDecodeError, TypeError):
        return 0, 0, 0, None
    return (
        meta.get("prompt_tokens", 0) or 0,
        meta.get("completion_tokens", 0) or 0,
        meta.get("total_tokens", 0) or 0,
        meta.get("error"),
    )


def run(
    contract_path: str,
    *,
    detector: str,
    critic: str,
    strategy: str = DEFAULT_STRATEGY,
) -> Prediction:
    """Run the detector -> critic pipeline on *contract_path*.

    Parameters
    ----------
    contract_path:
        Path to the .sol file.
    detector:
        Short model key (from ``SUPPORTED_MODELS``) used as the detector.
    critic:
        Short model key (from ``SUPPORTED_MODELS``) used as the critic.
        Should differ from *detector* (cross-model critique).
    strategy:
        Detector prompting strategy.  Defaults to ``chain_of_thought`` so the
        critic has reasoning to review.

    Returns
    -------
    Prediction
        Always returns — never raises.  The final ``vulnerabilities`` is the
        critic's revised list (or the detector's list if the critic call
        failed).  A full cost + behaviour breakdown is stored in raw_output.
    """
    if detector not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown detector model: {detector!r}. Use: {list(SUPPORTED_MODELS)}")
    if critic not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown critic model: {critic!r}. Use: {list(SUPPORTED_MODELS)}")

    path = Path(contract_path)
    contract_id = path.name
    tool_name = f"critique_{detector}_to_{critic}_{strategy}"
    start = time.monotonic()

    # ── Step 1: Detector ──────────────────────────────────────────────────
    detector_pred = single_agent_run(
        contract_path,
        strategy=strategy,
        model_id=SUPPORTED_MODELS[detector],
        tool_name=detector,
    )
    detector_classes = [v.vuln_class for v in detector_pred.vulnerabilities]
    detector_reasoning = _detector_reasoning(detector_pred)
    det_prompt_tok, det_comp_tok, det_total_tok, detector_error = _detector_tokens(detector_pred)

    # ── Step 2: Critic ────────────────────────────────────────────────────
    critic_response = ""
    crit_prompt_tok = crit_comp_tok = crit_total_tok = 0
    critic_error: Optional[str] = None
    critic_classes: list[str]

    try:
        contract_source = path.read_text(encoding="utf-8", errors="ignore")
        messages = critique_prompt.build_messages(
            contract_source, detector_classes, detector_reasoning
        )
        chat = call_chat(messages, SUPPORTED_MODELS[critic])
        critic_response = chat.response
        crit_prompt_tok = chat.prompt_tokens
        crit_comp_tok = chat.completion_tokens
        crit_total_tok = chat.total_tokens
        critic_error = chat.error

        if chat.error:
            # Critic failed — fall back to the detector's list so the pipeline
            # still has a prediction, but flag the error so analysis can
            # exclude this contract from "did critique help?" conclusions.
            critic_classes = list(detector_classes)
        else:
            critic_classes = [v.vuln_class for v in parse_vulnerabilities(critic_response)]
    except Exception as exc:  # noqa: BLE001
        critic_error = str(exc)
        critic_classes = list(detector_classes)

    # ── Behaviour breakdown (detector vs critic) ──────────────────────────
    det_set = set(detector_classes)
    crit_set = set(critic_classes)
    removed = sorted(det_set - crit_set)   # critic dropped these detector findings
    added = sorted(crit_set - det_set)     # critic introduced these new findings
    agreed = det_set == crit_set           # critic made no change

    # Final prediction = critic's revised list (deduplicated, canonical order).
    final_vulns = [Vulnerability(vuln_class=c) for c in sorted(crit_set)]

    elapsed = time.monotonic() - start

    total_prompt_tok = det_prompt_tok + crit_prompt_tok
    total_comp_tok = det_comp_tok + crit_comp_tok
    total_tok = det_total_tok + crit_total_tok

    raw = json.dumps({
        "strategy":          strategy,
        "detector_model":    detector,
        "detector_model_id": SUPPORTED_MODELS[detector],
        "critic_model":      critic,
        "critic_model_id":   SUPPORTED_MODELS[critic],
        # Behaviour
        "detector_classes":  sorted(det_set),
        "critic_classes":    sorted(crit_set),
        "removed":           removed,
        "added":             added,
        "agreed":            agreed,
        # Per-step tokens
        "detector_prompt_tokens":     det_prompt_tok,
        "detector_completion_tokens": det_comp_tok,
        "detector_total_tokens":      det_total_tok,
        "critic_prompt_tokens":       crit_prompt_tok,
        "critic_completion_tokens":   crit_comp_tok,
        "critic_total_tokens":        crit_total_tok,
        # Aggregate tokens (keys also consumed by the shared LLM logger)
        "prompt_tokens":     total_prompt_tok,
        "completion_tokens": total_comp_tok,
        "total_tokens":      total_tok,
        # Text
        "detector_response": detector_reasoning,
        "critic_response":   critic_response,
        "response":          critic_response,   # shared-logger "response" column
        # Errors
        "detector_error":    detector_error,
        "critic_error":      critic_error,
    }, ensure_ascii=False)

    return Prediction(
        contract_id=contract_id,
        tool_name=tool_name,
        vulnerabilities=final_vulns,
        runtime_seconds=round(elapsed, 3),
        tokens_used=total_tok,
        raw_output=raw,
    )


def make_tool(detector: str, critic: str, strategy: str = DEFAULT_STRATEGY):
    """Return a runner-compatible tool function for a detector/critic pair.

    Parameters
    ----------
    detector, critic:
        Short model keys from ``SUPPORTED_MODELS``.
    strategy:
        Detector prompting strategy (default ``chain_of_thought``).

    Returns
    -------
    Callable[[str], Prediction]
        Ready to pass to ``core.runner.run_evaluation``.
    """
    if detector not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown detector model: {detector!r}. Use: {list(SUPPORTED_MODELS)}")
    if critic not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown critic model: {critic!r}. Use: {list(SUPPORTED_MODELS)}")
    if strategy not in VALID_STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy!r}. Use: {VALID_STRATEGIES}")

    def _tool(contract_path: str) -> Prediction:
        return run(contract_path, detector=detector, critic=critic, strategy=strategy)

    _tool.__name__ = f"critique_{detector}_to_{critic}_{strategy}"
    return _tool


# ---------------------------------------------------------------------------
# Standalone smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 2 critique tool smoke-test.")
    parser.add_argument("--detector", default=list(SUPPORTED_MODELS)[0])
    parser.add_argument("--critic", default=list(SUPPORTED_MODELS)[-1])
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY, choices=VALID_STRATEGIES)
    parser.add_argument("contract", nargs="?", default=None)
    args = parser.parse_args()

    if args.contract:
        contract = args.contract
    else:
        dataset = _project_root / "shared" / "datasets" / "smartbugs-curated" / "dataset" / "access_control"
        candidates = sorted(dataset.glob("*.sol"))
        if not candidates:
            print("No .sol file found. Pass a path as argument.")
            sys.exit(1)
        contract = str(candidates[-1])

    print(f"Detector : {args.detector}")
    print(f"Critic   : {args.critic}")
    print(f"Strategy : {args.strategy}")
    print(f"Contract : {contract}\n")

    pred = run(contract, detector=args.detector, critic=args.critic, strategy=args.strategy)
    meta = json.loads(pred.raw_output or "{}")

    print(f"tool             : {pred.tool_name}")
    print(f"contract_id      : {pred.contract_id}")
    print(f"runtime          : {pred.runtime_seconds}s")
    print(f"detector classes : {meta.get('detector_classes')}")
    print(f"critic classes   : {meta.get('critic_classes')}  (final)")
    print(f"removed by critic : {meta.get('removed')}")
    print(f"added by critic   : {meta.get('added')}")
    print(f"agreed (no change): {meta.get('agreed')}")
    print(f"tokens (det/crit) : {meta.get('detector_total_tokens')}/{meta.get('critic_total_tokens')}"
          f"  total={meta.get('total_tokens')}")
    if meta.get("detector_error") or meta.get("critic_error"):
        print(f"detector_error   : {meta.get('detector_error')}")
        print(f"critic_error     : {meta.get('critic_error')}")
