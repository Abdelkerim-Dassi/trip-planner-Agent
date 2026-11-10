"""One-off model calls (reading itineraries, quick plans) that survive free tiers.

Free tiers answer bursts with "rate limit reached, try again in 5.7s", and
some run out for the day ("retry in 8h31m"). Every call therefore has a chain
of models: the one asked for, then the free fallbacks from
``config.fallback_models()``. A model that says it is busy is set aside for as
long as it asked and the next one is tried at once, so a visitor doesn't wait
on a model that has already said no. Only when every model is busy do we
wait, and then only for the shortest of the waits they asked for.
"""

from __future__ import annotations

import re
import threading
import time

from voyagent import config

#: Longest single wait we accept before giving up (seconds). A per-minute
#: window always clears within a minute.
MAX_WAIT_SECONDS = 65
#: Rounds through the whole chain before giving up.
RATE_LIMIT_RETRIES = 3
GEMINI_MIN_OUTPUT_TOKENS = 8000

# Groq: "try again in 5.7s" / "in 1m2.3s" / "in 350ms". Gemini: "retry in 8h31m21.3s".
_RETRY_AFTER = re.compile(
    r"(?:try again|retry) in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)(ms|s))?", re.IGNORECASE
)
_RETRY_DELAY = re.compile(r'"retryDelay":\s*"(\d+)s"')

#: model id -> time (monotonic) before which it is not worth calling again.
_cooldown: dict[str, float] = {}
_cooldown_lock = threading.Lock()


class ModelsBusyError(RuntimeError):
    """Every model in the chain is rate-limited for longer than we can wait."""


def _wait_seconds(message: str) -> float:
    """How long a rate-limit message asks us to wait (10 s when it doesn't say)."""
    delay = _RETRY_DELAY.search(message)
    if delay:
        return float(delay.group(1))
    match = _RETRY_AFTER.search(message)
    if not match or not any(match.groups()):
        return 10.0
    hours, minutes, amount, unit = match.groups()
    seconds = float(amount or 0) / (1000 if (unit or "s").lower() == "ms" else 1)
    return seconds + 60 * int(minutes or 0) + 3600 * int(hours or 0)


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
    if model.startswith("gemini/") and request.get("max_tokens"):
        # Gemini's thinking counts against the output limit: a budget sized
        # for another model leaves it a few hundred tokens for the answer,
        # and a plan comes back cut off after its first day.
        request["max_tokens"] = max(request["max_tokens"] * 3, GEMINI_MIN_OUTPUT_TOKENS)
    return request


def _chain(model: str) -> list[str]:
    return list(dict.fromkeys([model, *config.fallback_models()]))


def complete(**request):
    """``litellm.completion`` that rides out free-tier limits.

    Tries the requested model, then each fallback, skipping any that is in a
    cool-down. Raises :class:`ModelsBusyError` when all of them are busy for
    longer than ``MAX_WAIT_SECONDS``.
    """
    import litellm  # ships with crewai; imported lazily

    litellm.suppress_debug_info = True  # no help banner when a provider is busy
    models = _chain(request["model"])
    for round_number in range(RATE_LIMIT_RETRIES + 1):
        waits = []
        for model in models:
            with _cooldown_lock:
                remaining = _cooldown.get(model, 0) - time.monotonic()
            if remaining > 0:
                waits.append(remaining)
                continue
            try:
                return litellm.completion(**_for_model(request, model))
            except (litellm.RateLimitError, litellm.ServiceUnavailableError) as exc:
                wait = _wait_seconds(str(exc)) + 1
                with _cooldown_lock:
                    _cooldown[model] = time.monotonic() + wait
                waits.append(wait)
        shortest = min(waits)
        if shortest > MAX_WAIT_SECONDS or round_number == RATE_LIMIT_RETRIES:
            break
        time.sleep(max(shortest, 0.5))
    raise ModelsBusyError(
        "The free AI models are at their limit right now. Please try again in a few minutes."
    )


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

    # A model sometimes returns nothing usable (a thinking model that spends
    # its budget thinking, a small one that breaks the JSON), so an empty
    # answer gets one more try, then the main model.
    first = model or config.helper_model()
    attempts = [first, first]
    if config.litellm_model() != first:
        attempts.append(config.litellm_model())
    error: Exception | None = None
    answered = False
    for model_id in attempts:
        try:
            data = ask(model_id)
        except ModelsBusyError:
            raise  # the whole chain is busy: another attempt would only wait again
        except Exception as exc:  # outage, bad request: try the next model
            error = exc
            continue
        answered = True
        if data:
            return data
    if not answered and error is not None:
        raise error  # no model could be reached at all
    return {}
