"""
Multi-agent tool (Phase 3).

Three specialist agents plus a moderator, all using the SAME model in a given
run. Specialisation is by SYSTEM PROMPT ONLY (see ``prompts/``).

    contract ──▶ reentrancy specialist    ┐
             ──▶ access_control specialist ┼─(parallel)─▶ moderator ─▶ final classes
             ──▶ timestamp specialist      ┘  (sequential)

- Specialists run in PARALLEL (thread pool) with NO cross-visibility — each
  sees only the contract source.
- The moderator runs SEQUENTIALLY after all specialists complete, receiving the
  contract source plus every specialist's raw response verbatim, and returns
  the final vulnerability list (the prediction that gets scored).

From the harness's point of view this is still one tool with one
``run(contract_path) -> Prediction`` (the plug-in contract from Phase 0), so
``shared.core`` (schema/runner/scorer/logger) is untouched. The API client,
token counting, and parsing plumbing are REUSED from Phase 1's
``llm_single_agent`` (``call_chat`` etc.), not duplicated.

Graceful degradation: if a specialist call fails it is logged and treated as
empty findings; the moderator still runs on the survivors. If the contract
source alone exceeds the per-contract token cap, the contract is skipped and an
empty Prediction is returned with the reason recorded.

Everything is logged in ``raw_output``: every agent's raw response, per-call
token counts, and per-call runtimes.

Usage
-----
    from phases.phase3_multi_agent.tools.llm_multi_agent import make_tool
    tool_fn = make_tool(model="gpt4o-mini")
    prediction = tool_fn("/path/to/contract.sol")
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

# Allow running directly: python3 phases/phase3_multi_agent/tools/llm_multi_agent.py
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import Prediction, Vulnerability, VULNERABILITY_CLASSES
from shared.config.models import MODEL_CATALOG, PHASE3_TOKEN_CAP
# Reuse Phase 1's LLM plumbing (API client + token counting). Do NOT duplicate.
from phases.phase1_single_llm.tools.llm_single_agent import SUPPORTED_MODELS, call_chat
from phases.phase3_multi_agent.prompts import (
    reentrancy_specialist,
    access_control_specialist,
    timestamp_specialist,
    moderator as moderator_prompt,
)

# Ordered registry of specialists: (assigned_class, prompt_module).
# Order is canonical (matches VULNERABILITY_CLASSES) for deterministic output.
SPECIALISTS: list[tuple[str, object]] = [
    ("reentrancy", reentrancy_specialist),
    ("access_control", access_control_specialist),
    ("timestamp_dependency", timestamp_specialist),
]

DEFAULT_TOKEN_CAP = PHASE3_TOKEN_CAP  # per-contract source-size guard (tokens)

# Rough token estimate for the source-size guard. The shared chat client does
# not expose a tokenizer, and we must not duplicate/modify it, so we use the
# common ~4-characters-per-token heuristic. This only gates the skip decision.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Approximate the token count of *text* (~4 chars/token heuristic)."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _order_classes(classes: set[str]) -> list[str]:
    """Return *classes* in canonical order, filtered to known classes."""
    return [c for c in VULNERABILITY_CLASSES if c in classes]


def _iter_json_objects(text: str):
    """Yield every top-level ``{...}`` substring in *text* (brace-balanced).

    Handles nested braces and braces inside strings, so it works on
    ``{"findings": [{...}, {...}]}`` even when the model wraps it in prose.
    """
    depth = 0
    start: Optional[int] = None
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    yield text[start : i + 1]
                    start = None


def _parse_findings(response_text: str) -> tuple[list[str], list[dict]]:
    """Parse a ``{"findings": [...]}`` response.

    Returns ``(classes, findings)`` where *classes* are the canonical
    vulnerability classes present (deduplicated, canonical order) and
    *findings* is the raw list of finding dicts (kept for logging). Never
    raises — on any parse failure returns ``([], [])``.
    """
    if not response_text:
        return [], []

    text = response_text.strip()
    candidate: Optional[dict] = None

    # Prefer a strict parse of the whole payload; otherwise take the LAST
    # brace-balanced object that carries a "findings" key (handles preambles).
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "findings" in obj:
            candidate = obj
    except json.JSONDecodeError:
        pass

    if candidate is None:
        for chunk in _iter_json_objects(text):
            try:
                obj = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "findings" in obj:
                candidate = obj  # keep last

    if candidate is None:
        return [], []

    findings = candidate.get("findings")
    if not isinstance(findings, list):
        return [], []

    seen: set[str] = set()
    for f in findings:
        if isinstance(f, dict):
            vc = f.get("vuln_class")
            if isinstance(vc, str) and vc in VULNERABILITY_CLASSES:
                seen.add(vc)
    return _order_classes(seen), findings


def _run_specialist(
    assigned_class: str,
    prompt_module,
    contract_source: str,
    model_id: str,
) -> dict:
    """Run a single specialist. Never raises — failures are recorded in the dict.

    The specialist's returned classes are restricted to its assigned class, so
    a specialist can never contribute an out-of-scope class to the pipeline.
    """
    start = time.monotonic()
    messages = prompt_module.build_messages(contract_source)
    chat = call_chat(messages, model_id)
    elapsed = round(time.monotonic() - start, 3)

    if chat.error:
        return {
            "assigned_class": assigned_class,
            "response": "",
            "findings": [],
            "classes": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "runtime_seconds": elapsed,
            "error": chat.error,
        }

    classes, findings = _parse_findings(chat.response)
    # Enforce specialisation: keep only the assigned class.
    classes = [c for c in classes if c == assigned_class]
    return {
        "assigned_class": assigned_class,
        "response": chat.response,
        "findings": findings,
        "classes": classes,
        "prompt_tokens": chat.prompt_tokens,
        "completion_tokens": chat.completion_tokens,
        "total_tokens": chat.total_tokens,
        "runtime_seconds": elapsed,
        "error": None,
    }


def _tool_name(model: str, use_moderator: bool, active_classes: list[str]) -> str:
    """Build the Prediction.tool_name (also the results filename stem)."""
    name = f"multiagent_{model}"
    if not use_moderator:
        name += "_union"        # ablation: union of specialists, no moderator
    if len(active_classes) < len(SPECIALISTS):
        name += f"_{len(active_classes)}spec"   # ablation: fewer specialists
    return name


def run(
    contract_path: str,
    *,
    model: str,
    token_cap: Optional[int] = DEFAULT_TOKEN_CAP,
    use_moderator: bool = True,
    specialist_classes: Optional[list[str]] = None,
) -> Prediction:
    """Run the three-specialist + moderator pipeline on *contract_path*.

    Parameters
    ----------
    contract_path:
        Path to the .sol file.
    model:
        Short model key from ``MODEL_CATALOG``. ALL four agents use this model.
    token_cap:
        Per-contract source-size guard, in (estimated) tokens. If the contract
        source alone exceeds it, the contract is skipped and an empty
        Prediction is returned with the reason recorded. ``None`` disables it.
    use_moderator:
        If False, run the ablation: the final list is the deduplicated UNION of
        the specialist outputs (no moderator call).
    specialist_classes:
        Which specialists to run (subset of the three assigned classes).
        ``None`` runs all three. Used by the "2 specialists only" ablation.

    Returns
    -------
    Prediction
        Always returns — never raises. ``vulnerabilities`` is the moderator's
        final list (or the specialist union in the no-moderator ablation). Full
        per-agent detail is stored in ``raw_output``.
    """
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model: {model!r}. Use: {list(SUPPORTED_MODELS)}")

    model_id = SUPPORTED_MODELS[model]
    active = [
        (cls, mod)
        for cls, mod in SPECIALISTS
        if specialist_classes is None or cls in specialist_classes
    ]
    active_classes = [cls for cls, _ in active]

    path = Path(contract_path)
    contract_id = path.name
    tool_name = _tool_name(model, use_moderator, active_classes)
    start = time.monotonic()

    contract_source = path.read_text(encoding="utf-8", errors="ignore")
    source_tokens = _estimate_tokens(contract_source)

    # ── Token-cap guard: skip oversized contracts ─────────────────────────
    if token_cap is not None and source_tokens > token_cap:
        raw = json.dumps({
            "model": model,
            "model_id": model_id,
            "use_moderator": use_moderator,
            "active_specialists": active_classes,
            "token_cap": token_cap,
            "estimated_source_tokens": source_tokens,
            "skipped": True,
            "skip_reason": (
                f"contract source ~{source_tokens} tokens exceeds token_cap {token_cap}"
            ),
            "specialists": {},
            "moderator": {"ran": False},
            "final_classes": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }, ensure_ascii=False)
        return Prediction(
            contract_id=contract_id,
            tool_name=tool_name,
            vulnerabilities=[],
            runtime_seconds=round(time.monotonic() - start, 3),
            tokens_used=0,
            raw_output=raw,
        )

    # ── Step 1: specialists in parallel (no cross-visibility) ─────────────
    spec_start = time.monotonic()
    results: dict[str, dict] = {}
    if active:
        with ThreadPoolExecutor(max_workers=len(active)) as pool:
            futures = {
                pool.submit(_run_specialist, cls, mod, contract_source, model_id): cls
                for cls, mod in active
            }
            for fut in futures:
                r = fut.result()
                results[r["assigned_class"]] = r
    spec_elapsed = round(time.monotonic() - spec_start, 3)

    # Order specialist results canonically for stable logging/output.
    ordered = [results[cls] for cls in active_classes if cls in results]
    specialist_union = set()
    for r in ordered:
        specialist_union.update(r["classes"])

    # ── Step 2: moderator (sequential) or union ablation ──────────────────
    mod_meta: dict
    mod_elapsed = 0.0
    if use_moderator:
        spec_outputs = [
            {"specialist": r["assigned_class"], "response": r["response"], "classes": r["classes"]}
            for r in ordered
        ]
        mod_start = time.monotonic()
        messages = moderator_prompt.build_messages(contract_source, spec_outputs)
        chat = call_chat(messages, model_id)
        mod_elapsed = round(time.monotonic() - mod_start, 3)

        if chat.error:
            # Moderator failed — fall back to the specialist union so the
            # pipeline still yields a prediction, and record the error.
            final_classes = _order_classes(specialist_union)
            mod_meta = {
                "ran": True,
                "response": "",
                "findings": [],
                "classes": final_classes,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "runtime_seconds": mod_elapsed,
                "error": chat.error,
                "fell_back_to_union": True,
            }
        else:
            mclasses, mfindings = _parse_findings(chat.response)
            final_classes = _order_classes(set(mclasses))
            mod_meta = {
                "ran": True,
                "response": chat.response,
                "findings": mfindings,
                "classes": final_classes,
                "prompt_tokens": chat.prompt_tokens,
                "completion_tokens": chat.completion_tokens,
                "total_tokens": chat.total_tokens,
                "runtime_seconds": mod_elapsed,
                "error": None,
                "fell_back_to_union": False,
            }
    else:
        final_classes = _order_classes(specialist_union)
        mod_meta = {
            "ran": False,
            "response": "",
            "findings": [],
            "classes": final_classes,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "runtime_seconds": 0.0,
            "error": None,
            "fell_back_to_union": False,
        }

    # ── Aggregate tokens across all agents (per-role + total) ─────────────
    prompt_tokens = sum(r["prompt_tokens"] for r in ordered) + mod_meta["prompt_tokens"]
    completion_tokens = sum(r["completion_tokens"] for r in ordered) + mod_meta["completion_tokens"]
    total_tokens = sum(r["total_tokens"] for r in ordered) + mod_meta["total_tokens"]

    elapsed = round(time.monotonic() - start, 3)

    specialists_meta = {
        r["assigned_class"]: {
            "response": r["response"],
            "findings": r["findings"],
            "classes": r["classes"],
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "total_tokens": r["total_tokens"],
            "runtime_seconds": r["runtime_seconds"],
            "error": r["error"],
        }
        for r in ordered
    }

    raw = json.dumps({
        "model": model,
        "model_id": model_id,
        "use_moderator": use_moderator,
        "active_specialists": active_classes,
        "token_cap": token_cap,
        "estimated_source_tokens": source_tokens,
        "skipped": False,
        "specialists": specialists_meta,
        "moderator": mod_meta,
        "specialist_union_classes": _order_classes(specialist_union),
        "final_classes": final_classes,
        # Per-role token totals (agent role → tokens) for the cost breakdown.
        "role_tokens": {
            **{f"{cls}_specialist": specialists_meta.get(cls, {}).get("total_tokens", 0)
               for cls in active_classes},
            "moderator": mod_meta["total_tokens"],
        },
        "specialist_runtime_seconds": spec_elapsed,   # parallel wall time
        "moderator_runtime_seconds": mod_elapsed,
        # Aggregate tokens (keys also read by the shared LLM logger sidecar).
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }, ensure_ascii=False)

    return Prediction(
        contract_id=contract_id,
        tool_name=tool_name,
        vulnerabilities=[Vulnerability(vuln_class=c) for c in final_classes],
        runtime_seconds=elapsed,
        tokens_used=total_tokens,
        raw_output=raw,
    )


def make_tool(
    *,
    model: str,
    token_cap: Optional[int] = DEFAULT_TOKEN_CAP,
    use_moderator: bool = True,
    specialist_classes: Optional[list[str]] = None,
):
    """Return a runner-compatible ``(contract_path) -> Prediction`` closure.

    Parameters mirror :func:`run`. The returned callable is ready to pass to
    ``shared.core.runner.run_evaluation``.
    """
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model: {model!r}. Use: {list(SUPPORTED_MODELS)}")
    if specialist_classes is not None:
        unknown = [c for c in specialist_classes if c not in {cls for cls, _ in SPECIALISTS}]
        if unknown:
            raise ValueError(
                f"Unknown specialist class(es): {unknown}. "
                f"Use: {[cls for cls, _ in SPECIALISTS]}"
            )
        if not specialist_classes:
            raise ValueError("specialist_classes must not be empty.")

    active_classes = [
        cls for cls, _ in SPECIALISTS
        if specialist_classes is None or cls in specialist_classes
    ]

    def _tool(contract_path: str) -> Prediction:
        return run(
            contract_path,
            model=model,
            token_cap=token_cap,
            use_moderator=use_moderator,
            specialist_classes=specialist_classes,
        )

    _tool.__name__ = _tool_name(model, use_moderator, active_classes)
    return _tool


# ---------------------------------------------------------------------------
# Standalone smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 3 multi-agent tool smoke-test.")
    parser.add_argument("--model", default="gpt4o-mini")
    parser.add_argument("--token-cap", type=int, default=DEFAULT_TOKEN_CAP)
    parser.add_argument("--no-moderator", action="store_true")
    parser.add_argument("contract", nargs="?", default=None)
    args = parser.parse_args()

    if args.contract:
        contract = args.contract
    else:
        dataset = _project_root / "shared" / "datasets" / "smartbugs-curated" / "dataset" / "reentrancy"
        candidates = sorted(dataset.glob("*.sol"))
        if not candidates:
            print("No .sol file found. Pass a path as argument.")
            sys.exit(1)
        contract = str(candidates[0])

    print(f"Model      : {args.model}")
    print(f"Token cap  : {args.token_cap}")
    print(f"Moderator  : {not args.no_moderator}")
    print(f"Contract   : {contract}\n")

    pred = run(
        contract,
        model=args.model,
        token_cap=args.token_cap,
        use_moderator=not args.no_moderator,
    )
    meta = json.loads(pred.raw_output or "{}")

    print(f"tool             : {pred.tool_name}")
    print(f"contract_id      : {pred.contract_id}")
    print(f"runtime          : {pred.runtime_seconds}s  "
          f"(specialists {meta.get('specialist_runtime_seconds')}s parallel + "
          f"moderator {meta.get('moderator_runtime_seconds')}s)")
    print(f"skipped          : {meta.get('skipped')}")
    for cls, sm in meta.get("specialists", {}).items():
        note = f"  [FAILED: {sm['error']}]" if sm.get("error") else ""
        print(f"  {cls:<22}-> {sm.get('classes')}  ({sm.get('total_tokens')} tok){note}")
    mod = meta.get("moderator", {})
    mnote = f"  [FAILED: {mod['error']}]" if mod.get("error") else ""
    print(f"  {'moderator':<22}-> {mod.get('classes')}  ({mod.get('total_tokens')} tok){mnote}")
    print(f"final classes    : {[v.vuln_class for v in pred.vulnerabilities]}")
    print(f"total tokens     : {meta.get('total_tokens')}")
    print(f"role tokens      : {meta.get('role_tokens')}")
