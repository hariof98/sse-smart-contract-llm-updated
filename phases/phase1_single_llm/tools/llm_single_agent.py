"""
Single-agent LLM tool wrapper (Phase 1).

Uses the GitHub Models inference API (models.github.ai/inference) with a
GitHub Personal Access Token.  Supports three prompting strategies:
zero_shot, few_shot, chain_of_thought.

Each call returns a standard Prediction object (Phase 0 schema, untouched).
Token usage and the full prompt are stored in raw_output as a JSON string
so the Phase 1 logger can extract and persist them.

Usage
-----
    from phases.phase1_single_llm.tools.llm_single_agent import run
    prediction = run("/path/to/contract.sol", strategy="zero_shot")

    # Or as a runner-compatible closure:
    from phases.phase1_single_llm.tools.llm_single_agent import make_tool
    tool_fn = make_tool(strategy="few_shot")
    prediction = tool_fn("/path/to/contract.sol")
"""

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── sys.path bootstrap (allow running directly from any working dir) ────────
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.core.schema import Prediction, Vulnerability, VULNERABILITY_CLASSES
from shared.config.models import (
    MODEL_CATALOG,
    active_api_key_env,
    active_base_url,
    provider_model_id,
)

# ── Lazy import of openai (tell user clearly if missing) ───────────────────
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]

# ── .env loader (no external dependency) ───────────────────────────────────
def _load_env() -> None:
    """Read .env from the project root and inject values into os.environ."""
    import os
    env_path = _project_root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and value and key not in os.environ:
            os.environ[key] = value

_load_env()

# ── Configuration ───────────────────────────────────────────────────────────
import os

MAX_TOKENS       = 1024
TEMPERATURE      = 0.0   # deterministic — important for reproducibility
REQUEST_TIMEOUT  = 200   # seconds

# Reasoning models (GPT-5 family) consume a large internal "reasoning token"
# budget before producing any visible output, so they need a much larger token
# allowance.  They also reject custom temperature/top_p and require the
# max_completion_tokens parameter instead of max_tokens.
REASONING_MAX_TOKENS = 8192

# Provider base URL is resolved at call time from shared/config/models.py
# (GitHub Models by default; OpenAI when USE_OPENAI is set). This constant is
# kept for backwards compatibility only — call_chat uses active_base_url().
BASE_URL         = "https://models.github.ai/inference"

# Registry of supported models (name → GitHub Models ID).
# Single source of truth lives in shared/config/models.py — edit the catalog
# there to add or change models; this alias keeps existing imports working.
SUPPORTED_MODELS: dict[str, str] = MODEL_CATALOG

# Default model — the first model in the ACTIVE catalog (provider-safe, since
# the catalog switches with USE_OPENAI). Override via make_tool(model=...).
_DEFAULT_TOOL_NAME = next(iter(SUPPORTED_MODELS))
_DEFAULT_MODEL_ID  = SUPPORTED_MODELS[_DEFAULT_TOOL_NAME]

# Keep backwards-compatible module-level names
TOOL_NAME = _DEFAULT_TOOL_NAME
MODEL_ID  = _DEFAULT_MODEL_ID

# Map strategy name → prompt module
_STRATEGY_MODULES: dict[str, str] = {
    "zero_shot":        "phases.phase1_single_llm.prompts.zero_shot",
    "few_shot":         "phases.phase1_single_llm.prompts.few_shot",
    "chain_of_thought": "phases.phase1_single_llm.prompts.chain_of_thought",
}

VALID_STRATEGIES = list(_STRATEGY_MODULES.keys())


# ── Helpers ─────────────────────────────────────────────────────────────────

def _is_reasoning_model(model_id: str) -> bool:
    """True for GPT-5 family / o-series reasoning models that need special params.

    These models require ``max_completion_tokens`` instead of ``max_tokens`` and
    reject custom ``temperature``/``top_p``.
    """
    # Match with or without a provider prefix, so both the GitHub Models id
    # ("openai/o3") and the bare OpenAI id ("o3") are detected.
    mid = model_id.lower()
    base = mid.split("/", 1)[-1]
    return (
        "gpt-5" in mid
        or base.startswith("o1")
        or base.startswith("o3")
        or base.startswith("o4")
    )


def _is_deepseek_reasoning(model_id: str) -> bool:
    """True for DeepSeek-R1 reasoning models.

    R1 uses standard chat-completion params (``max_tokens`` + ``temperature``)
    but emits a long ``<think>...</think>`` reasoning block before the answer,
    so it needs a much larger token budget than non-reasoning models.
    """
    mid = model_id.lower()
    return "deepseek" in mid and "r1" in mid


def _get_prompt_module(strategy: str):
    """Import and return the prompt module for *strategy*."""
    if strategy not in _STRATEGY_MODULES:
        raise ValueError(
            f"Unknown strategy '{strategy}'. "
            f"Choose from: {VALID_STRATEGIES}"
        )
    import importlib
    return importlib.import_module(_STRATEGY_MODULES[strategy])


def _parse_vulnerabilities(response_text: str) -> list[Vulnerability]:
    """Extract vulnerability classes from the model's response.

    Tries strict JSON parse first, then falls back to regex extraction of
    the last JSON object in the text (handles chain-of-thought responses
    where reasoning precedes the final JSON).
    """
    text = response_text.strip()

    # 1. Try direct JSON parse (works for zero_shot / few_shot)
    try:
        data = json.loads(text)
        classes = data.get("vulnerabilities", [])
        return _classes_to_vulns(classes)
    except json.JSONDecodeError:
        pass

    # 2. Find the last {...} block in the text (chain_of_thought)
    matches = list(re.finditer(r'\{[^{}]*"vulnerabilities"[^{}]*\}', text, re.DOTALL))
    if matches:
        try:
            data = json.loads(matches[-1].group())
            classes = data.get("vulnerabilities", [])
            return _classes_to_vulns(classes)
        except json.JSONDecodeError:
            pass

    # 3. Fallback: scan for any of our class names mentioned in the text
    found = [c for c in VULNERABILITY_CLASSES if c in text.lower()]
    return _classes_to_vulns(found)


def _classes_to_vulns(classes: list) -> list[Vulnerability]:
    """Convert a list of class name strings to deduplicated Vulnerability objects."""
    seen: set[str] = set()
    vulns: list[Vulnerability] = []
    for cls in classes:
        if isinstance(cls, str) and cls in VULNERABILITY_CLASSES and cls not in seen:
            seen.add(cls)
            vulns.append(Vulnerability(vuln_class=cls))
    return vulns


def _make_raw_output(
    strategy: str,
    messages: list[dict],
    response_text: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    error: Optional[str] = None,
) -> str:
    """Serialise all run metadata to a JSON string stored in raw_output."""
    return json.dumps({
        "strategy":          strategy,
        "model":             MODEL_ID,
        "prompt_messages":   messages,
        "response":          response_text,
        "prompt_tokens":     prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens":      total_tokens,
        "error":             error,
    }, ensure_ascii=False)


# Public alias so other tools (e.g. the Phase 2 critic) can reuse the parser.
def parse_vulnerabilities(response_text: str) -> list[Vulnerability]:
    """Public wrapper around the response parser (see ``_parse_vulnerabilities``)."""
    return _parse_vulnerabilities(response_text)


# ── Shared chat helper ───────────────────────────────────────────────────────

@dataclass
class ChatResult:
    """Result of a single GitHub Models chat-completion call.

    Never carries an exception — any failure is reported in ``error`` while
    the token counts stay at zero and ``response`` is empty.
    """
    response: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error: Optional[str] = None


def call_chat(messages: list[dict], model_id: str) -> ChatResult:
    """Send *messages* to *model_id* via the GitHub Models API.

    This is the single place that knows how to talk to the API, including the
    parameter differences between standard models and reasoning models
    (GPT-5 / o-series use ``max_completion_tokens`` and reject custom
    temperature; DeepSeek-R1 needs a large ``max_tokens`` budget for its
    ``<think>`` block).  It never raises — errors are returned in the result.

    Both the Phase 1 single-agent tool and the Phase 2 critique tool use it,
    so model handling stays consistent across phases.
    """
    if OpenAI is None:
        return ChatResult(
            error="openai package not installed. Run: python3 -m pip install openai"
        )

    # Provider (GitHub Models vs OpenAI) is chosen by USE_OPENAI in
    # shared/config/models.py; resolve the key variable, base URL, and the
    # model-id format for whichever provider is active.
    api_key_env = active_api_key_env()
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        return ChatResult(
            error=f"{api_key_env} not set. Add it to .env or export it in your shell."
        )

    api_model_id = provider_model_id(model_id)

    try:
        client = OpenAI(base_url=active_base_url(), api_key=api_key, timeout=REQUEST_TIMEOUT)
        if _is_reasoning_model(api_model_id):
            # GPT-5 / o-series: max_completion_tokens, default temperature,
            # large budget to leave room for visible output after reasoning.
            resp = client.chat.completions.create(
                model=api_model_id,
                messages=messages,
                max_completion_tokens=REASONING_MAX_TOKENS,
            )
        elif _is_deepseek_reasoning(api_model_id):
            # DeepSeek-R1: standard params, large max_tokens so the final JSON
            # answer is not truncated by the long <think> block.
            resp = client.chat.completions.create(
                model=api_model_id,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=REASONING_MAX_TOKENS,
            )
        else:
            resp = client.chat.completions.create(
                model=api_model_id,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                top_p=1,
            )
        return ChatResult(
            response=resp.choices[0].message.content or "",
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
            total_tokens=resp.usage.total_tokens,
        )
    except Exception as exc:  # noqa: BLE001
        return ChatResult(error=str(exc))


# ── Public API ───────────────────────────────────────────────────────────────

def run(
    contract_path: str,
    strategy: str = "zero_shot",
    *,
    model_id: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> Prediction:
    """Run a GitHub Models LLM on *contract_path* with the given *strategy*.

    Parameters
    ----------
    contract_path:
        Path to the .sol file.
    strategy:
        One of ``"zero_shot"``, ``"few_shot"``, ``"chain_of_thought"``.
    model_id:
        GitHub Models model ID (e.g. ``"openai/gpt-4o-mini"``).
        Defaults to the module-level ``MODEL_ID``.
    tool_name:
        Label stored in Prediction.tool_name.
        Defaults to the module-level ``TOOL_NAME``.

    Returns
    -------
    Prediction
        Always returns — never raises.  Errors are captured in raw_output.
    """
    _model_id  = model_id  or MODEL_ID
    _tool_name = tool_name or TOOL_NAME
    path = Path(contract_path)
    contract_id = path.name
    start = time.monotonic()

    vulns: list[Vulnerability] = []
    prompt_tokens = completion_tokens = total_tokens = 0
    response_text = ""
    messages: list[dict] = []
    error_msg: Optional[str] = None

    try:
        # ── Read contract source ───────────────────────────────────────────
        contract_source = path.read_text(encoding="utf-8", errors="ignore")

        # ── Build prompt ───────────────────────────────────────────────────
        prompt_mod = _get_prompt_module(strategy)
        messages = prompt_mod.build_messages(contract_source)

        # ── Call API (shared helper, never raises) ─────────────────────────
        chat = call_chat(messages, _model_id)
        response_text     = chat.response
        prompt_tokens     = chat.prompt_tokens
        completion_tokens = chat.completion_tokens
        total_tokens      = chat.total_tokens

        if chat.error:
            error_msg = chat.error
        else:
            vulns = _parse_vulnerabilities(response_text)

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)

    elapsed = time.monotonic() - start

    raw = _make_raw_output(
        strategy=strategy,
        messages=messages,
        response_text=response_text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        error=error_msg,
    )

    return Prediction(
        contract_id=contract_id,
        tool_name=f"{_tool_name}_{strategy}",
        vulnerabilities=vulns,
        runtime_seconds=round(elapsed, 3),
        tokens_used=total_tokens,
        raw_output=raw,
    )


def make_tool(strategy: str, model: str | None = None):
    """Return a runner-compatible tool function for *strategy* and *model*.

    Parameters
    ----------
    strategy:
        One of ``VALID_STRATEGIES``.
    model:
        Short model key from the ACTIVE ``SUPPORTED_MODELS`` catalog. Defaults
        to the first model in that catalog (provider-safe).

    Returns
    -------
    Callable[[str], Prediction]
        Ready to pass to ``core.runner.run_evaluation``.
    """
    if strategy not in VALID_STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy!r}. Use: {VALID_STRATEGIES}")
    if model is None:
        model = _DEFAULT_TOOL_NAME
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model: {model!r}. Use: {list(SUPPORTED_MODELS)}")

    _mid  = SUPPORTED_MODELS[model]
    _tname = model  # e.g. "gpt-4o-mini", "o3"

    def _tool(contract_path: str) -> Prediction:
        return run(contract_path, strategy=strategy, model_id=_mid, tool_name=_tname)

    _tool.__name__ = f"{_tname}_{strategy}"
    return _tool


# ── Standalone smoke-test ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="zero_shot", choices=VALID_STRATEGIES)
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

    print(f"Strategy : {args.strategy}")
    print(f"Contract : {contract}")
    print()

    pred = run(contract, strategy=args.strategy)
    raw = json.loads(pred.raw_output or "{}")

    print(f"tool            : {pred.tool_name}")
    print(f"contract_id     : {pred.contract_id}")
    print(f"runtime         : {pred.runtime_seconds}s")
    print(f"findings        : {[v.vuln_class for v in pred.vulnerabilities]}")
    print(f"prompt_tokens   : {raw.get('prompt_tokens', 'n/a')}")
    print(f"completion_tokens: {raw.get('completion_tokens', 'n/a')}")
    print(f"total_tokens    : {raw.get('total_tokens', 'n/a')}")
    if raw.get("error"):
        print(f"error           : {raw['error']}")
    print()
    print("── Response ──────────────────────────────────────────────────────")
    print(raw.get("response", "(empty)"))
