"""Central configuration: environment loading, key validation, and model setup.

Keeping this dependency-light (no crewai import) so it can be imported and tested
in isolation. The LLM factory is the single place that decides which model the
agents use.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load .env once, on import.
load_dotenv()

# --- Provider & model configuration --------------------------------------------

#: Which LLM provider the agents use: "openai" (default) or "groq".
#: Groq exposes an OpenAI-compatible API with a free tier (https://console.groq.com).
PROVIDER = os.environ.get("VOYAGENT_PROVIDER", "openai").lower()

#: Sensible default model per provider. Override with VOYAGENT_MODEL.
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
}

#: The chat model every agent uses. Change it here once, not per-agent.
MODEL_NAME = os.environ.get(
    "VOYAGENT_MODEL", _DEFAULT_MODELS.get(PROVIDER, "gpt-4o-mini")
)

#: Sampling temperature for the agents.
MODEL_TEMPERATURE = float(os.environ.get("VOYAGENT_TEMPERATURE", "0.2"))

# --- Required secrets ----------------------------------------------------------

#: The API key each provider needs for the LLM.
_PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
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


def build_llm():
    """Build the shared chat model for the agents.

    Imports are lazy so that importing this module does not require ``langchain``
    or ``crewai`` to be installed (useful for config-only tests).

    For ``groq`` we use ``crewai.LLM`` (backed by LiteLLM, which ships with
    crewai) and the ``groq/`` model prefix — no extra dependency needed.
    """
    if PROVIDER == "groq":
        from crewai import LLM

        # Groq's free tier has a tokens-per-minute cap. num_retries lets LiteLLM
        # wait out the 429 (it honours Groq's retry-after hint) and continue,
        # so a run completes on the free tier instead of crashing mid-crew.
        return LLM(
            model=f"groq/{MODEL_NAME}",
            temperature=MODEL_TEMPERATURE,
            api_key=os.environ.get("GROQ_API_KEY"),
            num_retries=int(os.environ.get("GROQ_NUM_RETRIES", "8")),
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=MODEL_NAME, temperature=MODEL_TEMPERATURE)
