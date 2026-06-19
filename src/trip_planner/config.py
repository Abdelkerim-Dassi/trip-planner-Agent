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

# --- Model configuration -------------------------------------------------------

#: The chat model every agent uses. Change it here once, not per-agent.
MODEL_NAME = os.environ.get("TRIP_PLANNER_MODEL", "gpt-4o-mini")

#: Sampling temperature for the agents.
MODEL_TEMPERATURE = float(os.environ.get("TRIP_PLANNER_TEMPERATURE", "0.2"))

# --- Required secrets ----------------------------------------------------------

REQUIRED_KEYS = ("OPENAI_API_KEY", "SERPER_API_KEY")


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

    Imported lazily so that importing this module does not require ``langchain``
    to be installed (useful for config-only tests).
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=MODEL_NAME, temperature=MODEL_TEMPERATURE)
