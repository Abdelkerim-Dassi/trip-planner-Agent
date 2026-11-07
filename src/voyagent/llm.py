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


def complete_json(prompt: str, model: str | None = None, max_tokens: int = 3000) -> dict:
    """Ask for a JSON object and parse it; ``{}`` when the reply has none.

    Uses JSON mode where the provider accepts it. Groq rejects a reply that
    fails its strict JSON check instead of returning it, so on that error we
    ask again without JSON mode and pull the object out of the text ourselves.
    """
    import json

    import litellm

    def ask(model_id: str) -> dict:
        request = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "num_retries": 2,
        }
        try:
            response = complete(**request, response_format={"type": "json_object"})
        except litellm.BadRequestError:
            response = complete(**request)
        content = response.choices[0].message.content or ""
        match = re.search(r"\{.*\}", content, re.S)
        try:
            data = json.loads(match.group(0)) if match else {}
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    # Thinking models (Gemini Flash) sometimes spend the whole token budget
    # thinking and return nothing, so an empty answer gets one more try, then
    # the main model; so does a helper that is down or out of quota.
    first = model or config.helper_model()
    attempts = [first, first]
    if config.litellm_model() != first:
        attempts.append(config.litellm_model())
    error: Exception | None = None
    answered = False
    for model_id in attempts:
        try:
            data = ask(model_id)
        except Exception as exc:  # rate limit, outage: try the next model
            error = exc
            continue
        answered = True
        if data:
            return data
    if not answered and error is not None:
        raise error  # no model could be reached at all
    return {}
