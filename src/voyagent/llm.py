"""One-off model calls (TikTok extraction, quick plans) that survive free tiers.

Free tiers answer bursts with "rate limit reached, try again in 5.7s". When a
second free provider is configured (``config.fallback_model()``), a busy or
overloaded primary hands the request straight to it, so a visitor doesn't
wait. Without one, we wait as long as the provider asks: LiteLLM's own
retries back off for a second or two, too short for a per-minute window.
"""

from __future__ import annotations

import re
import time

from voyagent import config

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


def _for_model(request: dict, model: str) -> dict:
    request = {**request, "model": model}
    extra = dict(request.pop("extra_body", None) or {})
    extra.pop("reasoning_effort", None)
    if "gpt-oss" in model:
        # Sent raw: this LiteLLM version rejects reasoning_effort for Groq,
        # although Groq's API accepts it. Thinking briefly saves a large share
        # of the free per-minute token budget.
        extra["reasoning_effort"] = "low"
    if extra:
        request["extra_body"] = extra
    return request


def complete(**request):
    """``litellm.completion`` that rides out free-tier limits.

    Tries the requested model; if it is rate-limited or overloaded, moves to
    the fallback model when one is configured, otherwise waits as asked.
    """
    import litellm  # ships with crewai; imported lazily

    models = [request["model"]]
    fallback = config.fallback_model()
    if fallback and fallback != request["model"]:
        models.append(fallback)

    for index, model in enumerate(models):
        has_next = index + 1 < len(models)
        attempt_request = _for_model(request, model)
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                return litellm.completion(**attempt_request)
            except (litellm.RateLimitError, litellm.ServiceUnavailableError) as exc:
                if has_next:
                    break  # hand over to the next free provider right away
                wait = _wait_seconds(str(exc)) + 1
                if attempt == RATE_LIMIT_RETRIES or wait > MAX_WAIT_SECONDS:
                    raise
                time.sleep(wait)
    raise RuntimeError("unreachable")  # the last model either returns or raises
