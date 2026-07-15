"""
Single source of truth for model selection across all phases.

If you want to change which model a phase uses, edit ONLY this file — every
run script (Phase 1, Phase 2, ...) reads its defaults from here. You never
need to touch the individual ``run.py`` files just to swap a model.

What lives here
---------------
1. ``USE_OPENAI`` — the provider toggle (GitHub Models free tier vs live OpenAI).
2. Two provider-scoped catalogs, and ``MODEL_CATALOG`` — the ACTIVE one, chosen
   by the toggle. Each maps a short CLI key (e.g. ``"gpt-4o-mini"``) to the exact
   model id that provider expects.
3. Per-phase selections — which model(s) each phase uses by default. These are
   also chosen per provider so a default is always valid for the active catalog.
4. ``COST_PER_1M`` — approximate list pricing per model, used only for the
   informational cost estimates in the reports.

Provider model availability
----------------------------
  USE_OPENAI = False  (GitHub Models, free)  ->  gpt-4o-mini, gpt-4o
  USE_OPENAI = True   (live OpenAI, paid)     ->  gpt-4.1-nano, gpt-5.5, o3

Only the models in the ACTIVE catalog can be selected (``--model``); picking a
model from the other provider is rejected with "Unknown model".
"""

# ── 1. Provider toggle: GitHub Models (default) vs live OpenAI ──────────────
# Flip this ONE flag to switch every LLM phase between providers:
#   USE_OPENAI = False  -> GitHub Models free tier   (reads GITHUB_TOKEN)
#   USE_OPENAI = True   -> live OpenAI API            (reads OPENAI_API_KEY)
# The shared LLM client (phase1's llm_single_agent) reads the helpers below to
# pick the right base URL, API-key variable, and catalog automatically — no
# other code needs to change.
USE_OPENAI: bool = True

GITHUB_BASE_URL: str = "https://models.github.ai/inference"
OPENAI_BASE_URL: str = "https://api.openai.com/v1"

# ── 2. Provider-scoped model catalogs: short key → provider model id ────────
# GitHub Models uses an "openai/..." prefix; the live OpenAI API uses the bare
# id. Each catalog therefore stores ids already in that provider's format.
GITHUB_MODEL_CATALOG: dict[str, str] = {
    "gpt-4o-mini": "openai/gpt-4o-mini",
    "gpt-4o":      "openai/gpt-4o",
}

OPENAI_MODEL_CATALOG: dict[str, str] = {
    "gpt-4.1-nano": "gpt-4.1-nano",
    "gpt-5.5":      "gpt-5.5",
    "o3":           "o3",
}

# The ACTIVE catalog. Everything downstream (SUPPORTED_MODELS, --model
# validation, per-phase defaults) uses this.
MODEL_CATALOG: dict[str, str] = (
    OPENAI_MODEL_CATALOG if USE_OPENAI else GITHUB_MODEL_CATALOG
)


def active_base_url() -> str:
    """Return the inference base URL for the active provider."""
    return OPENAI_BASE_URL if USE_OPENAI else GITHUB_BASE_URL


def active_api_key_env() -> str:
    """Return the environment-variable name holding the active provider's key."""
    return "OPENAI_API_KEY" if USE_OPENAI else "GITHUB_TOKEN"


def provider_model_id(catalog_id: str) -> str:
    """Return the provider-native model id for a catalog value.

    Each provider has its own catalog whose values are already the exact ids
    that provider expects (GitHub keeps the ``"openai/"`` prefix; OpenAI uses
    the bare id), so this is a pass-through kept as a single stable call site.
    """
    return catalog_id


# ── 3. Per-phase model selection (per provider) ────────────────────────────
# Defaults are chosen per provider so they are always valid for the active
# catalog. CLI flags (--model / --critic) still override these at run time.
if USE_OPENAI:
    # Live OpenAI (paid): gpt-4.1-nano, gpt-5.5, o3
    PHASE1_MODEL: str = "gpt-4.1-nano"
    PHASE2_DETECTOR: str = "gpt-4.1-nano"   # cheap detector
    PHASE2_CRITIC: str = "o3"               # strong critic (cross-model)
    PHASE3_MODEL: str = "gpt-4.1-nano"
    PHASE4_MODEL: str = "gpt-4.1-nano"
else:
    # GitHub Models (free): gpt-4o-mini, gpt-4o
    PHASE1_MODEL = "gpt-4o-mini"
    PHASE2_DETECTOR = "gpt-4o-mini"          # cheap detector
    PHASE2_CRITIC = "gpt-4o"                 # stronger critic (cross-model)
    PHASE3_MODEL = "gpt-4o-mini"
    PHASE4_MODEL = "gpt-4o-mini"

PHASE1_STRATEGY: str = "chain_of_thought"
PHASE2_STRATEGY: str = "chain_of_thought"

# Phase 3 per-contract source-size guard (estimated tokens). If a contract's
# source alone exceeds this, the contract is skipped. See phase3 --token-cap.
PHASE3_TOKEN_CAP: int = 20000

# ── 4. Pricing (informational only) ────────────────────────────────────────
# Approximate list pricing, USD per 1M tokens: (input, output). Used only for
# the "estimated cost" lines in reports. A model omitted here simply shows a
# cost estimate of "n/a"; accuracy metrics are unaffected.
COST_PER_1M: dict[str, tuple[float, float]] = {
    #               input $/1M   output $/1M
    "gpt-4o-mini":   (0.15,       0.60),
    "gpt-4o":        (2.50,      10.00),
    "gpt-4.1-nano": (0.10,       0.40),
    # Add o3 / gpt-5.5 list prices here when known.
}
