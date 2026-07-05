"""
Single source of truth for model selection across all phases.

If you want to change which model a phase uses, edit ONLY this file — every
run script (Phase 1, Phase 2, ...) reads its defaults from here. You never
need to touch the individual ``run.py`` files just to swap a model.

Three things live here:

1. ``MODEL_CATALOG`` — the master registry of every model we can call, mapping
   a short key (e.g. ``"gpt4o-mini"``) to its GitHub Models API id
   (e.g. ``"openai/gpt-4o-mini"``). Add a new model here once and it becomes
   usable everywhere.

2. Per-phase selections — which model(s) each phase uses by default:
     • ``PHASE1_MODEL``
     • ``PHASE2_DETECTOR`` / ``PHASE2_CRITIC``
   plus the default prompting strategy per phase.

3. ``COST_PER_1M`` — approximate OpenAI list pricing per model, used only for
   the informational cost estimates in the reports (the actual calls go through
   the GitHub Models free tier).

Quota note
----------
On the GitHub Models free tier the "mini"/"nano" models (gpt4o-mini,
gpt41-nano) have much higher request limits than the full models (gpt4o,
gpt41, gpt5). If a phase keeps hitting "Too many requests" (HTTP 429), switch
its selection here to a mini/nano model.
"""

# ── 1. Master model catalog: short key → GitHub Models API id ──────────────
# Add a model here once to make it available to every phase.
MODEL_CATALOG: dict[str, str] = {
    "gpt4o-mini":  "openai/gpt-4o-mini",
    "gpt4o":       "openai/gpt-4o",
    "gpt41":       "openai/gpt-4.1",
    "gpt41-nano":  "openai/gpt-4.1-nano",
    "gpt5":        "openai/gpt-5",
    "gpt5-mini":   "openai/gpt-5-mini",
    "deepseek-r1": "deepseek/DeepSeek-R1-0528",
}

# ── 2. Per-phase model selection ───────────────────────────────────────────
# Change these to swap the default model for a phase. Each must be a key that
# exists in MODEL_CATALOG above. (CLI flags like --model / --critic still
# override these at run time.)

# Phase 1 — single-model LLM evaluation.
PHASE1_MODEL: str = "gpt4o"
PHASE1_STRATEGY: str = "chain_of_thought"

# Phase 2 — two-agent detector -> critic pipeline (cross-model critique).
# The critic defaults to a low-tier model (gpt41-nano) with a higher free-tier
# quota so the pipeline does not immediately hit rate limits on the critic call.
PHASE2_DETECTOR: str = "gpt4o-mini"
PHASE2_CRITIC: str = "gpt41-nano"
PHASE2_STRATEGY: str = "chain_of_thought"

# Phase 3 — multi-agent (3 specialists + moderator). ALL four agents use the
# SAME model in a given run; specialisation is by system prompt only. Phase 3
# reuses the model aliases above — no new model IDs are required.
PHASE3_MODEL: str = "gpt4o-mini"
# Per-contract source-size guard (estimated tokens). If a contract's source
# alone exceeds this, the contract is skipped. See phase3 run.py --token-cap.
PHASE3_TOKEN_CAP: int = 20000

# Phase 4 — hybrid: LLM filters cached Slither (Phase 0) findings. One LLM call
# per contract (skipped when Slither found nothing in scope). Reuses the model
# aliases above — no new model IDs are required.
PHASE4_MODEL: str = "gpt4o-mini"

# ── 3. Pricing (informational only) ────────────────────────────────────────
# Approximate OpenAI list pricing, USD per 1M tokens: (input, output).
# Used for the "estimated cost" lines in reports; actual calls are free-tier.
COST_PER_1M: dict[str, tuple[float, float]] = {
    #             input $/1M   output $/1M
    "gpt4o-mini":  (0.15,       0.60),
    "gpt4o":       (2.50,      10.00),
    "gpt41":       (2.00,       8.00),
    "gpt41-nano":  (0.10,       0.40),
    "gpt5":        (2.00,      10.00),
    "gpt5-mini":   (0.25,       2.00),
    "deepseek-r1": (0.0,        0.0),   # free via GitHub Models
}
