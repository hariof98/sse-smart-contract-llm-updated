"""
Hybrid tool (Phase 4) — LLM as a filter over Slither's output.

Pattern: reuse the cached Phase 0 Slither findings, keep only the in-scope ones,
and ask an LLM (in a single call) to CONFIRM or REJECT each. The final prediction
is the CONFIRMED subset. The LLM may NOT add findings Slither did not report —
this is a filter-only design (no augmentation).

    cached Slither findings ──(filter in-scope)──▶ LLM review (confirm/reject) ──▶ final classes

Key efficiency property: if Slither reported ZERO in-scope findings for a
contract, the LLM call is skipped entirely (tokens = 0). That skip is a real
cost saving of the hybrid pattern and is logged/measured.

From the harness's view this is still one tool with one
``run(contract_path) -> Prediction`` (the Phase 0 plug-in contract), so
``shared.core`` is untouched. Slither is NOT re-run — the cached Phase 0 JSON is
read. The Slither detector→class mapping and the LLM API client are REUSED from
Phase 0 / Phase 1, not duplicated.

Usage
-----
    from phases.phase4_hybrid.tools.llm_hybrid import make_tool
    tool_fn = make_tool(model="gpt-4o-mini")
    prediction = tool_fn("/path/to/contract.sol")
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

# Allow running directly: python3 phases/phase4_hybrid/tools/llm_hybrid.py
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import Prediction, Vulnerability, VULNERABILITY_CLASSES
# Reuse Phase 1's LLM plumbing (API client + token counting). Do NOT duplicate.
from phases.phase1_single_llm.tools.llm_single_agent import SUPPORTED_MODELS, call_chat
# Reuse Phase 0's Slither detector→class mapping. Do NOT duplicate.
from phases.phase0_traditional.tools.slither_tool import DETECTOR_TO_CLASS
from phases.phase4_hybrid.prompts import filter_review as filter_prompt

# In-scope classes are derived from the Phase 0 mapping table (reuse, not a copy).
IN_SCOPE_CLASSES: set[str] = set(DETECTOR_TO_CLASS.values())

_PHASE0_RESULTS_DIR = _project_root / "results" / "phase0_traditional"

# Cache of {resolved_slither_json_path: {contract_id: [in_scope_class, ...]}}.
_SLITHER_INDEX_CACHE: dict[str, dict[str, list[str]]] = {}


def find_latest_slither_results(results_dir: Optional[Path] = None) -> Optional[Path]:
    """Return the newest cached ``slither_*.json`` in the Phase 0 results dir."""
    d = Path(results_dir) if results_dir is not None else _PHASE0_RESULTS_DIR
    if not d.exists():
        return None
    candidates = sorted(d.glob("slither_*.json"))
    # Exclude any analysis side-files (e.g. *_comparison.json) defensively.
    candidates = [c for c in candidates if "_comparison" not in c.name]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load_slither_index(slither_results_path: Path) -> dict[str, list[str]]:
    """Load & memoise a {contract_id: [in-scope classes]} index from cached JSON.

    The Phase 0 base logger stores each contract's Slither prediction as
    ``pred_classes`` (already mapped to canonical classes via
    ``DETECTOR_TO_CLASS``), keyed by ``contract_id`` (``folder/file.sol``).
    """
    key = str(slither_results_path.resolve())
    if key in _SLITHER_INDEX_CACHE:
        return _SLITHER_INDEX_CACHE[key]

    payload = json.loads(slither_results_path.read_text(encoding="utf-8"))
    index: dict[str, list[str]] = {}
    for entry in payload.get("contracts", []):
        cid = entry.get("contract_id", "")
        preds = entry.get("pred_classes", []) or []
        in_scope = [c for c in preds if c in IN_SCOPE_CLASSES]
        index[cid] = in_scope
    _SLITHER_INDEX_CACHE[key] = index
    return index


def _cache_key(path: Path) -> str:
    """Reconstruct the Phase 0 contract_id (``folder/file.sol``) from a path."""
    return f"{path.parent.name}/{path.name}"


def _order_classes(classes: set[str]) -> list[str]:
    """Return *classes* in canonical order, filtered to known classes."""
    return [c for c in VULNERABILITY_CLASSES if c in classes]


def _iter_json_objects(text: str):
    """Yield every top-level ``{...}`` substring in *text* (brace-balanced)."""
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


def _parse_reviewed(response_text: str) -> list[dict]:
    """Parse a ``{"reviewed": [...]}`` response. Never raises — [] on failure."""
    if not response_text:
        return []
    text = response_text.strip()

    candidate: Optional[dict] = None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "reviewed" in obj:
            candidate = obj
    except json.JSONDecodeError:
        pass

    if candidate is None:
        for chunk in _iter_json_objects(text):
            try:
                obj = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "reviewed" in obj:
                candidate = obj  # keep last

    if candidate is None:
        return []
    reviewed = candidate.get("reviewed")
    return reviewed if isinstance(reviewed, list) else []


def _decisions(reviewed: list[dict], in_scope: set[str]) -> tuple[list[str], list[str]]:
    """Split reviewed items into (confirmed, rejected) canonical class lists.

    Enforces the filter-only rule: a class is only counted if it was actually in
    the Slither in-scope set, so the LLM can never add a new finding.
    """
    confirmed: set[str] = set()
    rejected: set[str] = set()
    for item in reviewed:
        if not isinstance(item, dict):
            continue
        orig = item.get("original_finding") or {}
        vc = orig.get("vuln_class") if isinstance(orig, dict) else None
        if not isinstance(vc, str) or vc not in in_scope:
            continue  # augmentation guard: ignore anything not from Slither
        decision = str(item.get("decision", "")).strip().lower()
        if decision == "confirmed":
            confirmed.add(vc)
        elif decision == "rejected":
            rejected.add(vc)
    return _order_classes(confirmed), _order_classes(rejected)


def run(
    contract_path: str,
    *,
    model: str,
    slither_results_path: Optional[str | Path] = None,
) -> Prediction:
    """Run the Slither→LLM filter pipeline on *contract_path*.

    Parameters
    ----------
    contract_path:
        Path to the .sol file.
    model:
        Short model key from ``SUPPORTED_MODELS`` used for the review call.
    slither_results_path:
        Path to a cached Phase 0 ``slither_*.json``. If None, the newest one in
        ``results/phase0_traditional/`` is used.

    Returns
    -------
    Prediction
        Always returns — never raises. ``vulnerabilities`` are the LLM-confirmed
        findings (a subset of Slither's in-scope findings). Full detail is in
        ``raw_output``.
    """
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model: {model!r}. Use: {list(SUPPORTED_MODELS)}")

    model_id = SUPPORTED_MODELS[model]
    path = Path(contract_path)
    contract_id = path.name
    tool_name = f"hybrid_slither_{model}"
    start = time.monotonic()

    slither_path = (
        Path(slither_results_path) if slither_results_path is not None
        else find_latest_slither_results()
    )

    # ── Locate cached Slither findings ────────────────────────────────────
    if slither_path is None or not slither_path.exists():
        raw = json.dumps({
            "model": model, "model_id": model_id,
            "slither_results_file": str(slither_path) if slither_path else None,
            "slither_in_scope_findings": [],
            "skipped_llm": True,
            "skip_reason": "no cached Slither results found (run Phase 0 slither first)",
            "llm_response": "", "reviewed": [],
            "confirmed_classes": [], "rejected_classes": [],
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "error": "missing_slither_cache",
        }, ensure_ascii=False)
        return Prediction(
            contract_id=contract_id, tool_name=tool_name, vulnerabilities=[],
            runtime_seconds=round(time.monotonic() - start, 3),
            tokens_used=0, raw_output=raw,
        )

    index = _load_slither_index(slither_path)
    key = _cache_key(path)
    in_scope_list = index.get(key)
    if in_scope_list is None:
        in_scope_list = index.get(path.name, [])   # fallback by basename
    in_scope_list = _order_classes(set(in_scope_list))
    slither_findings = [{"vuln_class": c} for c in in_scope_list]

    # ── Skip path: Slither found nothing in scope → no LLM call ───────────
    if not in_scope_list:
        raw = json.dumps({
            "model": model, "model_id": model_id,
            "slither_results_file": str(slither_path),
            "slither_in_scope_findings": [],
            "skipped_llm": True,
            "skip_reason": "Slither reported zero in-scope findings",
            "llm_response": "", "reviewed": [],
            "confirmed_classes": [], "rejected_classes": [],
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "error": None,
        }, ensure_ascii=False)
        return Prediction(
            contract_id=contract_id, tool_name=tool_name, vulnerabilities=[],
            runtime_seconds=round(time.monotonic() - start, 3),
            tokens_used=0, raw_output=raw,
        )

    # ── Single LLM review call ────────────────────────────────────────────
    contract_source = path.read_text(encoding="utf-8", errors="ignore")
    messages = filter_prompt.build_messages(contract_source, slither_findings)
    chat = call_chat(messages, model_id)

    error_msg: Optional[str] = chat.error
    reviewed: list[dict] = []
    if chat.error:
        # LLM failed — no confirmed findings; record the error. (Conservative:
        # a failed reviewer confirms nothing rather than passing Slither through.)
        confirmed_classes: list[str] = []
        rejected_classes: list[str] = []
    else:
        reviewed = _parse_reviewed(chat.response)
        confirmed_classes, rejected_classes = _decisions(reviewed, set(in_scope_list))

    elapsed = round(time.monotonic() - start, 3)

    raw = json.dumps({
        "model": model, "model_id": model_id,
        "slither_results_file": str(slither_path),
        "slither_in_scope_findings": in_scope_list,
        "skipped_llm": False,
        "skip_reason": None,
        "llm_response": chat.response,
        "reviewed": reviewed,
        "confirmed_classes": confirmed_classes,
        "rejected_classes": rejected_classes,
        "prompt_tokens": chat.prompt_tokens,
        "completion_tokens": chat.completion_tokens,
        "total_tokens": chat.total_tokens,
        "error": error_msg,
    }, ensure_ascii=False)

    return Prediction(
        contract_id=contract_id,
        tool_name=tool_name,
        vulnerabilities=[Vulnerability(vuln_class=c) for c in confirmed_classes],
        runtime_seconds=elapsed,
        tokens_used=chat.total_tokens,
        raw_output=raw,
    )


def make_tool(*, model: str, slither_results_path: Optional[str | Path] = None):
    """Return a runner-compatible ``(contract_path) -> Prediction`` closure.

    Parameters mirror :func:`run`. The Slither index is loaded lazily and
    memoised on first use, so passing an explicit *slither_results_path* pins the
    whole run to one cached Phase 0 result.
    """
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model: {model!r}. Use: {list(SUPPORTED_MODELS)}")

    def _tool(contract_path: str) -> Prediction:
        return run(contract_path, model=model, slither_results_path=slither_results_path)

    _tool.__name__ = f"hybrid_slither_{model}"
    return _tool


# ---------------------------------------------------------------------------
# Standalone smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 4 hybrid tool smoke-test.")
    parser.add_argument("--model", default=next(iter(SUPPORTED_MODELS)))
    parser.add_argument("--slither-results", default=None)
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

    latest = find_latest_slither_results()
    print(f"Model            : {args.model}")
    print(f"Slither cache    : {args.slither_results or latest}")
    print(f"Contract         : {contract}\n")

    pred = run(contract, model=args.model, slither_results_path=args.slither_results)
    meta = json.loads(pred.raw_output or "{}")
    print(f"tool             : {pred.tool_name}")
    print(f"contract_id      : {pred.contract_id}")
    print(f"slither in-scope : {meta.get('slither_in_scope_findings')}")
    print(f"skipped LLM      : {meta.get('skipped_llm')}  ({meta.get('skip_reason')})")
    print(f"confirmed        : {meta.get('confirmed_classes')}")
    print(f"rejected         : {meta.get('rejected_classes')}")
    print(f"final classes    : {[v.vuln_class for v in pred.vulnerabilities]}")
    print(f"tokens           : {meta.get('total_tokens')}")
    if meta.get("error"):
        print(f"error            : {meta.get('error')}")
