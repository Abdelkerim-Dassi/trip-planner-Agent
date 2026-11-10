"""Offline tests for the daily limits, the shared counter and the search client."""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
import requests  # noqa: E402

from voyagent import limits, serper, storage  # noqa: E402

SERPER_HITS = [{"title": "Bardo", "link": "https://example.com/bardo", "snippet": "Mosaics", "position": 1}]
TAVILY_HITS = [{"title": "Medina", "url": "https://example.com/medina", "content": "Old town", "score": 0.9}]


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code, self.text = payload, status_code, str(payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    for name in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "TAVILY_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SERPER_API_KEY", "serper-test-key")
    monkeypatch.setattr(limits, "SEARCH_BUDGET", 200)
    limits._counts.clear()
    serper._cache.clear()
    yield
    limits._counts.clear()
    serper._cache.clear()


@pytest.fixture
def http(monkeypatch):
    """Replace ``requests.post``; records the host of every call."""
    calls = []
    answers = {
        "google.serper.dev": lambda: FakeResponse({"organic": SERPER_HITS}),
        "api.tavily.com": lambda: FakeResponse({"query": "q", "results": TAVILY_HITS}),
    }

    def fake_post(url, **kwargs):
        host = url.split("/")[2]
        calls.append(SimpleNamespace(host=host, kwargs=kwargs))
        return answers[host]()

    monkeypatch.setattr(requests, "post", fake_post)
    return SimpleNamespace(calls=calls, answers=answers, hosts=lambda: [c.host for c in calls])


# --- limits -------------------------------------------------------------------


def test_allow_blocks_after_limit_per_ip_and_per_kind():
    assert [limits.allow("check", "1.2.3.4", 3) for _ in range(4)] == [True, True, True, False]
    assert not limits.allow("check", "1.2.3.4", 3)  # stays blocked
    assert limits.allow("check", "5.6.7.8", 3)  # another visitor is unaffected
    assert limits.allow("plan", "1.2.3.4", 3)  # and so is another kind


def test_allow_unlimited_when_limit_is_zero():
    assert all(limits.allow("check", "1.2.3.4", 0) for _ in range(50))
    assert limits._counts == {}


def test_allow_resets_on_a_new_day(monkeypatch):
    monkeypatch.setattr(limits, "_today", lambda: "2026-11-10")
    assert limits.allow("check", "1.2.3.4", 1)
    assert not limits.allow("check", "1.2.3.4", 1)
    monkeypatch.setattr(limits, "_today", lambda: "2026-11-11")
    assert limits.allow("check", "1.2.3.4", 1)
    assert all(key.endswith("2026-11-11") for key in limits._counts)  # yesterday was pruned


def test_spend_global_budget():
    assert limits.spend("search", 5, amount=3)
    assert not limits.spend("search", 5, amount=3)  # 6 would go over
    assert limits.spend("search", 5, amount=2)
    assert not limits.spend("search", 5)
    assert limits.spend("mcp", 5)  # budgets are per kind
    assert limits.spend("search", 0)  # unlimited


def test_allow_uses_larger_shared_count_and_never_stores_raw_ip(monkeypatch):
    keys = []

    def fake_incr(key, ttl_seconds, amount=1):
        keys.append(key)
        return 7  # e.g. counted before a restart

    monkeypatch.setattr(storage, "incr", fake_incr)
    assert limits.allow("check", "203.0.113.9", 10)  # 7 of 10
    assert not limits.allow("plan", "203.0.113.9", 5)  # 7 of 5, though only 1 seen here
    assert len(keys) == 2 and all("203.0.113.9" not in key for key in keys)
    assert all(storage._COUNTER_KEY.match(key) for key in keys)
    # Once known to be over, Upstash isn't asked again.
    assert not limits.allow("plan", "203.0.113.9", 5)
    assert len(keys) == 2


def test_allow_survives_a_broken_counter(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("upstash down")

    monkeypatch.setattr(storage, "incr", boom)
    assert limits.allow("check", "1.2.3.4", 1)
    assert not limits.allow("check", "1.2.3.4", 1)


def test_client_ip():
    behind_proxy = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.9, 10.0.0.1"}, client=SimpleNamespace(host="10.0.0.1")
    )
    direct = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    assert limits.client_ip(behind_proxy) == "203.0.113.9"
    assert limits.client_ip(direct) == "127.0.0.1"
    assert limits.client_ip(SimpleNamespace(headers={}, client=None)) == "unknown"


# --- storage.incr ---------------------------------------------------------------


def test_incr_sets_expiry_on_first_use_only(monkeypatch):
    commands = []
    values = iter([1, 2])

    def fake_redis(*command):
        commands.append(command)
        return next(values) if command[0] == "INCR" else 1

    monkeypatch.setattr(storage, "_redis", fake_redis)
    assert storage.incr("search:2026-11-10", 3600) == 1
    assert storage.incr("search:2026-11-10", 3600) == 2
    assert commands == [
        ("INCR", "reeltrip:count:search:2026-11-10"),
        ("EXPIRE", "reeltrip:count:search:2026-11-10", "3600"),
        ("INCR", "reeltrip:count:search:2026-11-10"),
    ]


def test_incr_without_upstash_and_bad_key():
    assert storage.incr("search:2026-11-10", 3600) is None
    with pytest.raises(ValueError):
        storage.incr("bad key/../x", 3600)


# --- search: caches -------------------------------------------------------------


def test_persistent_cache_survives_a_restart(http):
    assert serper.search("  bardo museum hours ")[0]["link"] == "https://example.com/bardo"
    serper._cache.clear()  # what a restart does
    assert serper.search("bardo museum hours") == SERPER_HITS
    assert serper.search("bardo museum hours") == SERPER_HITS  # now from memory
    assert http.hosts() == ["google.serper.dev"]


def test_persistent_cache_expires_after_seven_days(http):
    serper.search("bardo museum hours")
    key = serper._store_key("bardo museum hours")
    record = storage.load("search", key)
    assert len(key) == 32 and record["results"] == SERPER_HITS

    record["t"] = time.time() - 6 * 24 * 3600
    storage.save("search", key, record)
    serper._cache.clear()
    serper.search("bardo museum hours")
    assert len(http.calls) == 1  # six days old: still good

    record["t"] = time.time() - 8 * 24 * 3600
    storage.save("search", key, record)
    serper._cache.clear()
    serper.search("bardo museum hours")
    assert len(http.calls) == 2  # eight days old: fetched again
    assert storage.load("search", key)["t"] > time.time() - 60  # and stored anew


def test_fresh_search_skips_reading_caches_but_writes_them(http):
    serper.search("bardo museum hours")
    serper.fresh_search("bardo museum hours")
    assert len(http.calls) == 2
    serper._cache.clear()
    serper.search("bardo museum hours")
    assert len(http.calls) == 2


def test_empty_answers_are_not_cached(http):
    http.answers["google.serper.dev"] = lambda: FakeResponse({"organic": []})
    assert serper.search("nothing here") == []
    assert serper.search("nothing here") == []
    assert len(http.calls) == 2
    assert storage.load("search", serper._store_key("nothing here")) is None


# --- search: daily budget ---------------------------------------------------------


def test_daily_budget_raises_without_http_call(http, monkeypatch):
    monkeypatch.setattr(limits, "SEARCH_BUDGET", 2)
    serper.search("one")
    serper.search("two")
    serper.search("one")  # cached answers are free
    with pytest.raises(serper.SearchError, match="budget is used up"):
        serper.search("three")
    assert len(http.calls) == 2
    assert serper.search("two") == SERPER_HITS  # the cache still answers


# --- search: Tavily -----------------------------------------------------------------


def test_tavily_for_normal_queries_serper_for_tiktok(http, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    assert serper.search("tunis medina walking route") == [
        {"title": "Medina", "link": "https://example.com/medina", "snippet": "Old town"}
    ]
    assert serper.search("site:TikTok.com tunis food") == SERPER_HITS
    assert http.hosts() == ["api.tavily.com", "google.serper.dev"]

    tavily_call = http.calls[0].kwargs
    assert tavily_call["headers"]["Authorization"] == "Bearer tvly-test-key"
    assert tavily_call["json"]["query"] == "tunis medina walking route"
    assert tavily_call["timeout"] == 15
    assert limits._counts == {f"search:{limits._today()}": 1}  # only Serper spends budget


@pytest.mark.parametrize(
    "tavily_answer",
    [
        lambda: FakeResponse({"detail": {"error": "Unauthorized: missing or invalid API key."}}, 401),
        lambda: FakeResponse({"query": "q", "results": []}),
        lambda: (_ for _ in ()).throw(requests.ConnectionError("no route")),
        lambda: FakeResponse(["not", "a", "dict"]),
    ],
)
def test_tavily_failure_falls_back_to_serper(http, monkeypatch, tavily_answer):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    http.answers["api.tavily.com"] = tavily_answer
    assert serper.search("tunis medina walking route") == SERPER_HITS
    assert http.hosts() == ["api.tavily.com", "google.serper.dev"]


def test_tavily_answers_when_serper_budget_is_gone(http, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    monkeypatch.setattr(limits, "SEARCH_BUDGET", 1)
    serper.search("tiktok.com/@someone/video/1")
    assert serper.search("tunis medina walking route")[0]["link"] == "https://example.com/medina"
    with pytest.raises(serper.SearchError, match="budget is used up"):
        serper.search("tiktok.com/@someone/video/2")
    assert http.hosts() == ["google.serper.dev", "api.tavily.com"]


def test_search_only_raises_search_error(http, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    http.answers["api.tavily.com"] = lambda: FakeResponse({"detail": {"error": "limit"}}, 432)
    http.answers["google.serper.dev"] = lambda: (_ for _ in ()).throw(KeyError("surprise"))
    with pytest.raises(serper.SearchError):
        serper.search("tunis medina walking route")

    monkeypatch.delenv("SERPER_API_KEY")
    with pytest.raises(serper.SearchError, match="SERPER_API_KEY"):
        serper.search("tiktok tunis")
