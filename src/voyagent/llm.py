"""One-off model calls (TikTok extraction, quick plans) that survive free tiers.

Free tiers answer bursts with "rate limit reached, try again in 5.7s". LiteLLM's
own retries back off for a second or two, which is too short for a
tokens-per-minute window, so here we wait as long as the provider asks.
"""

from __future__ import annotations

import re
import time

#: Longest single wait we accept before giving up (seconds).
MAX_WAIT_SECONDS = 30
RATE_LIMIT_RETRIES = 3

_RETRY_AFTER = re.compile(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)", re.IGNORECASE)


def _wait_seconds(message: str) -> float:
    match = _RETRY_AFTER.search(message)
    if not match:
        return 10.0
    minutes, amount, unit = match.groups()
    seconds = float(amount) / (1000 if unit.lower() == "ms" else 1)
    return seconds + 60 * int(minutes or 0)


def complete(**request):
    """``litellm.completion`` that waits out rate limits as the provider asks.

    Reasoning models (gpt-oss) are told to think briefly, which saves a large
    share of the free per-minute token budget.
    """
    import litellm  # ships with crewai; imported lazily

    if "gpt-oss" in request.get("model", ""):
        # Sent raw: this LiteLLM version rejects reasoning_effort for Groq,
        # although Groq's API accepts it for gpt-oss models.
        request.setdefault("extra_body", {}).setdefault("reasoning_effort", "low")
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return litellm.completion(**request)
        except litellm.RateLimitError as exc:
            wait = _wait_seconds(str(exc)) + 1
            if attempt == RATE_LIMIT_RETRIES or wait > MAX_WAIT_SECONDS:
                raise
            time.sleep(wait)
