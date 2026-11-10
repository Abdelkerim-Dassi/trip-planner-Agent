"""Central configuration: environment loading, key validation, and model setup.

Keeping this dependency-light (no crewai import) so it can be imported and tested
in isolation. The LLM factory is the single place that decides which model the
agents use.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

# Load .env once, on import.
load_dotenv()

# The HTTP client logs every request URL at INFO, and Gemini's URL carries the
# API key ("?key=..."). Keep those lines out of the logs, here and on the host.
for _noisy in ("httpx", "httpcore", "LiteLLM", "litellm"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# --- Provider & model configuration --------------------------------------------

#: Which LLM provider the agents use: "openai" (default), "groq" or "gemini".
#: Groq (https://console.groq.com) and Gemini (https://aistudio.google.com) both
#: have free tiers that need no credit card.
PROVIDER = os.environ.get("VOYAGENT_PROVIDER", "openai").lower()

#: Sensible default model per provider. Override with VOYAGENT_MODEL.
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    # Groq retired llama-3.3-70b-versatile; gpt-oss-120b is on its free tier.
    "groq": "openai/gpt-oss-120b",
    # Flash-Lite: the full Flash model allows only ~20 free requests a day.
    "gemini": "gemini-3.5-flash-lite",
}

#: The chat model every agent uses. Change it here once, not per-agent.
MODEL_NAME = os.environ.get(
    "VOYAGENT_MODEL", _DEFAULT_MODELS.get(PROVIDER, "gpt-4o-mini")
)

#: Sampling temperature for the agents.
MODEL_TEMPERATURE = float(os.environ.get("VOYAGENT_TEMPERATURE", "0.2"))

#: Pause between agent steps, to stay under free-tier per-minute limits
#: (Groq: 8k tokens/min; Gemini Flash: about 10 requests/min). 0 disables it.
_DEFAULT_STEP_DELAYS = {"groq": "10", "gemini": "6"}
STEP_DELAY_SECONDS = float(
    os.environ.get(
        "VOYAGENT_STEP_DELAY_SECONDS",
        os.environ.get("GROQ_STEP_DELAY_SECONDS", _DEFAULT_STEP_DELAYS.get(PROVIDER, "0")),
    )
)

#: How plans are made: "crew" (seven agents, best on OpenAI or Gemini) or
#: "quick" (one grounded call; fits Groq's 8k-tokens-a-minute free tier, where
#: the crew cannot run). Defaults to "quick" on Groq.
PLAN_MODE = os.environ.get(
    "VOYAGENT_PLAN_MODE", "quick" if PROVIDER == "groq" else "crew"
).lower()

# --- Required secrets ----------------------------------------------------------

#: The API key each provider needs for the LLM.
_PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

#: SERPER_API_KEY powers web search; the provider's key powers the agents.
REQUIRED_KEYS = (
    _PROVIDER_KEYS.get(PROVIDER, "OPENAI_API_KEY"),
    "SERPER_API_KEY",
)


class MissingConfigError(RuntimeError):
    """Raised when a required environment variable is not set."""


def validate_env() -> None:
    """Fail fast with a clear message if any required key is missing.

    Call this once at startup so users get a readable error instead of a deep
    ``KeyError`` from inside a tool call mid-run.
    """
    missing = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
    if missing:
        raise MissingConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ".\nCopy .env.example to .env and fill in your API keys."
        )


def litellm_model() -> str:
    """The configured agent model as a LiteLLM model id."""
    return MODEL_NAME if PROVIDER == "openai" else f"{PROVIDER}/{MODEL_NAME}"


#: Groq's small, fast model. It has its own rate limit, separate from the
#: plan writer's, and answers short extraction jobs in under a second.
_FAST_GROQ_MODEL = "groq/qwen/qwen3.8-27b"
#: Gemini's Flash-Lite. The full Flash model allows only about 20 free
#: requests a day and can take a minute to answer; Flash-Lite does neither.
_FREE_GEMINI_MODEL = "gemini/gemini-3.5-flash-lite"


def discovery_model() -> str:
    """LiteLLM model id for the short, frequent jobs a visitor waits on:
    listing the places in an itinerary or in TikTok captions, and reading
    opening hours during a check.

    On Groq this defaults to the small fast model, so these jobs don't use up
    the plan writer's per-minute budget. Override with VOYAGENT_DISCOVERY_MODEL.
    """
    return os.environ.get("VOYAGENT_DISCOVERY_MODEL") or (
        _FAST_GROQ_MODEL if PROVIDER == "groq" else litellm_model()
    )


def fallback_models() -> list[str]:
    """Free models to try, in order, when the one asked for is rate-limited or
    overloaded.

    Defaults to Groq's fast model (when a Groq key is set) and then Gemini
    Flash-Lite (when a Gemini key is set). Set VOYAGENT_FALLBACK_MODEL to a
    comma-separated list of LiteLLM model ids to choose your own, or to "" for
    none.
    """
    configured = os.environ.get("VOYAGENT_FALLBACK_MODEL")
    if configured is not None:
        return [m.strip() for m in configured.split(",") if m.strip()]
    models = []
    if os.environ.get("GROQ_API_KEY"):
        models.append(_FAST_GROQ_MODEL)
    if os.environ.get("GEMINI_API_KEY") and PROVIDER != "gemini":
        models.append(_FREE_GEMINI_MODEL)
    return [m for m in models if m != litellm_model()]


def fallback_model() -> str:
    """The first fallback model ("" for none); see :func:`fallback_models`."""
    models = fallback_models()
    return models[0] if models else ""


def helper_model() -> str:
    """LiteLLM model id for small background jobs (captions, the older
    opening-hours check). Defaults to the discovery model; override with
    VOYAGENT_HELPER_MODEL.
    """
    return os.environ.get("VOYAGENT_HELPER_MODEL") or discovery_model()


def build_llm():
    """Build the shared chat model for the agents.

    Imports are lazy so that importing this module does not require ``langchain``
    or ``crewai`` to be installed (useful for config-only tests).

    For ``groq`` and ``gemini`` we use ``crewai.LLM`` (backed by LiteLLM, which
    ships with crewai) with the provider's model prefix — no extra dependency.
    """
    if PROVIDER != "openai":
        from crewai import LLM

        # Free tiers cap requests/tokens per minute. num_retries lets LiteLLM
        # wait out the 429 (honouring the retry-after hint) and continue, so a
        # run completes instead of crashing mid-crew.
        return LLM(
            model=litellm_model(),
            temperature=MODEL_TEMPERATURE,
            api_key=os.environ.get(_PROVIDER_KEYS.get(PROVIDER, "")),
            num_retries=int(
                os.environ.get("VOYAGENT_NUM_RETRIES", os.environ.get("GROQ_NUM_RETRIES", "8"))
            ),
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=MODEL_NAME, temperature=MODEL_TEMPERATURE)
