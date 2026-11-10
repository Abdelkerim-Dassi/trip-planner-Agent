"""Offline tests for the model chain: busy models are skipped, not waited on."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import litellm  # noqa: E402
import pytest  # noqa: E402

from voyagent import config, llm  # noqa: E402


def busy(message):
    return litellm.RateLimitError(message, llm_provider="test", model="test")


@pytest.fixture
def chain(monkeypatch):
    monkeypatch.setattr(llm, "_cooldown", {})
    monkeypatch.setattr(config, "fallback_models", lambda: ["fast", "lite"])
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    return sleeps


@pytest.mark.parametrize(
    ("message", "seconds"),
    [
        ("Rate limit reached. Please try again in 5.7s.", 5.7),
        ("try again in 1m2.5s", 62.5),
        ("try again in 350ms", 0.35),
        ("Please retry in 8h31m21.3s.", 8 * 3600 + 31 * 60 + 21.3),
        ('"retryDelay": "30681s"', 30681),
        ("no hint at all", 10),
    ],
)
def test_wait_seconds(message, seconds):
    assert llm._wait_seconds(message) == pytest.approx(seconds)


def test_busy_model_is_skipped_at_once_and_stays_skipped(chain, monkeypatch):
    calls = []

    def fake(**request):
        calls.append(request["model"])
        if request["model"] == "main":
            raise busy("Quota exceeded, per day. Please retry in 8h31m21s.")
        return SimpleNamespace(model=request["model"])

    monkeypatch.setattr(litellm, "completion", fake)
    assert llm.complete(model="main", messages=[]).model == "fast"
    assert llm.complete(model="main", messages=[]).model == "fast"
    assert calls == ["main", "fast", "fast"]  # the exhausted model isn't asked twice
    assert chain == []  # and nobody waited for it


def test_waits_for_the_shortest_limit_when_every_model_is_busy(chain, monkeypatch):
    state = {"round": 0}

    def fake(**request):
        if state["round"] == 0:
            raise busy({"main": "try again in 20s", "fast": "try again in 4s", "lite": "retry in 9h0m0s"}[request["model"]])
        return SimpleNamespace(model=request["model"])

    def sleep(seconds):
        chain.append(seconds)
        state["round"] = 1
        llm._cooldown.clear()  # time has passed

    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(llm.time, "sleep", sleep)
    assert llm.complete(model="main", messages=[]).model == "main"
    assert chain == [pytest.approx(5.0)]


def test_gives_up_with_a_message_when_all_are_out_for_hours(chain, monkeypatch):
    monkeypatch.setattr(litellm, "completion", lambda **r: (_ for _ in ()).throw(busy("retry in 8h0m0s")))
    with pytest.raises(llm.ModelsBusyError, match="try again in a few minutes"):
        llm.complete(model="main", messages=[])
    assert chain == []


def test_gemini_gets_room_to_think():
    assert llm._for_model({"model": "x", "max_tokens": 3500}, "gemini/gemini-3.5-flash-lite")["max_tokens"] == 10500
    assert llm._for_model({"model": "x", "max_tokens": 3500}, "groq/openai/gpt-oss-120b")["max_tokens"] == 3500
