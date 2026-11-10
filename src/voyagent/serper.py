"""Web search client, shared by the agent tool and the TikTok discovery / MCP
tools.

Serper.dev (Google results) is the main provider. Its free allowance is a
one-time 2,500 queries, so every query is guarded three ways:

- answers are cached in memory and, for a week, in ``storage`` (which survives
  restarts when Upstash is configured);
- a daily budget (``limits.SEARCH_BUDGET``) caps real Serper calls;
- when ``TAVILY_API_KEY`` is set, searches that don't need Google's TikTok
  index go to Tavily first (free 1,000 a month) and only fall back to Serper.

Kept free of ``crewai`` so the web app and MCP server can import it cheaply.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict

import requests

from voyagent import limits, storage

log = logging.getLogger(__name__)

SEARCH_URL = "https://google.serper.dev/search"
TAVILY_URL = "https://api.tavily.com/search"
REQUEST_TIMEOUT_SECONDS = 15
CACHE_SECONDS = 7 * 24 * 3600
TAVILY_MAX_RESULTS = 10
_CACHE_SIZE = 512
_STORE_KIND = "search"
_BUDGET_MESSAGE = "Today's free search budget is used up. Please try again tomorrow."

# query -> (unix time the answer was fetched, results)
_cache: OrderedDict[str, tuple[float, tuple[dict, ...]]] = OrderedDict()
_cache_lock = threading.Lock()


class SearchError(RuntimeError):
    """Raised when search is unreachable, misconfigured, over budget or rejects the query."""


def search(query: str) -> list[dict]:
    """Return organic web results (``title``, ``link``, ``snippet``) for ``query``.

    Results are cached per query, in memory and for a week in ``storage``,
    which saves credits when several users explore the same destination. Empty
    answers are never cached: a provider occasionally returns nothing for a
    query that works a minute later, and caching that would break the query
    for a week.
    """
    query = query.strip()
    cached = _recall(query)
    if cached is None:
        stored = _load_stored(query)
        if stored is not None:
            fetched_at, cached = stored
            _remember(query, cached, fetched_at)
    if cached is not None:
        return list(cached)

    results = _fetch(query)
    if results:
        _remember(query, results, time.time())
        _store(query, results)
    return list(results)


def fresh_search(query: str) -> list[dict]:
    """Like :func:`search` but skips the caches, and replaces the cached answer
    when the fresh one has results."""
    query = query.strip()
    results = _fetch(query)
    if results:
        _remember(query, results, time.time())
        _store(query, results)
    return list(results)


# --- caches -----------------------------------------------------------------


def _is_fresh(fetched_at: float) -> bool:
    return time.time() - fetched_at < CACHE_SECONDS


def _recall(query: str) -> tuple[dict, ...] | None:
    with _cache_lock:
        entry = _cache.get(query)
        if entry is None:
            return None
        if not _is_fresh(entry[0]):
            del _cache[query]
            return None
        _cache.move_to_end(query)
        return entry[1]


def _remember(query: str, results: tuple[dict, ...], fetched_at: float) -> None:
    with _cache_lock:
        _cache[query] = (fetched_at, results)
        _cache.move_to_end(query)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)


def _store_key(query: str) -> str:
    return hashlib.sha1(query.encode("utf-8")).hexdigest()[:32]


def _load_stored(query: str) -> tuple[float, tuple[dict, ...]] | None:
    """The stored answer and when it was fetched, if there is one under a week old."""
    try:
        record = storage.load(_STORE_KIND, _store_key(query))
        if not isinstance(record, dict):
            return None
        fetched_at = float(record.get("t") or 0)
        results = record.get("results")
        if not (isinstance(results, list) and results and _is_fresh(fetched_at)):
            return None
        return fetched_at, tuple(r for r in results if isinstance(r, dict))
    except Exception as exc:  # a broken cache must never break a search
        log.debug("Stored search answer unreadable: %s", exc)
        return None


def _store(query: str, results: tuple[dict, ...]) -> None:
    try:
        storage.save(
            _STORE_KIND,
            _store_key(query),
            {"t": time.time(), "results": list(results)},
            ttl_seconds=CACHE_SECONDS,
        )
    except Exception as exc:
        log.debug("Could not store search answer: %s", exc)


# --- providers --------------------------------------------------------------


def _fetch(query: str) -> tuple[dict, ...]:
    """Ask a provider. Raises nothing but :class:`SearchError`."""
    try:
        tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
        # TikTok lookups need Google's index, so they always go to Serper.
        if not tavily_key or "tiktok" in query.lower():
            return _serper(query)

        try:
            results = _tavily(query, tavily_key)
        except SearchError as exc:
            log.debug("Tavily search failed, trying Serper: %s", exc)
            return _serper(query)
        if results:
            return results
        try:
            return _serper(query)
        except SearchError as exc:
            # Tavily did answer, with nothing; that stands when Serper can't help.
            log.debug("Serper unavailable after an empty Tavily answer: %s", exc)
            return ()
    except SearchError:
        raise
    except Exception as exc:
        raise SearchError(f"Search failed: {type(exc).__name__}") from exc


def _serper(query: str) -> tuple[dict, ...]:
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        raise SearchError("SERPER_API_KEY is not set in the environment.")
    if not limits.spend("search", limits.SEARCH_BUDGET):
        raise SearchError(_BUDGET_MESSAGE)

    try:
        response = requests.post(
            SEARCH_URL,
            headers={"X-API-KEY": api_key, "content-type": "application/json"},
            data=json.dumps({"q": query}),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise SearchError(f"Search request failed: {exc}") from exc

    if response.status_code != 200:
        # Serper explains rejections (bad key, exhausted credits) in "message".
        try:
            message = response.json().get("message", "")
        except (ValueError, AttributeError):
            message = response.text[:200]
        raise SearchError(f"Search failed ({response.status_code}): {message}")

    try:
        organic = response.json().get("organic")
    except (ValueError, AttributeError) as exc:
        raise SearchError("Search returned an unreadable answer.") from exc
    if not isinstance(organic, list):
        return ()
    return tuple(r for r in organic if isinstance(r, dict))


def _tavily(query: str, api_key: str) -> tuple[dict, ...]:
    """Tavily's search API (https://docs.tavily.com/documentation/api-reference/endpoint/search),
    with results reshaped to Serper's ``title`` / ``link`` / ``snippet``.

    ``search_depth`` is pinned to ``basic`` so a search costs one credit.
    """
    try:
        response = requests.post(
            TAVILY_URL,
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json={"query": query, "search_depth": "basic", "max_results": TAVILY_MAX_RESULTS},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise SearchError(f"Tavily request failed: {exc}") from exc

    if response.status_code != 200:
        # Tavily explains rejections in {"detail": {"error": "..."}}.
        try:
            detail = response.json().get("detail")
            message = detail.get("error", "") if isinstance(detail, dict) else str(detail)[:200]
        except (ValueError, AttributeError):
            message = response.text[:200]
        raise SearchError(f"Tavily search failed ({response.status_code}): {message}")

    try:
        items = response.json().get("results")
    except (ValueError, AttributeError) as exc:
        raise SearchError("Tavily returned an unreadable answer.") from exc
    if not isinstance(items, list):
        return ()
    return tuple(
        {
            "title": str(item.get("title") or ""),
            "link": str(item.get("url") or ""),
            "snippet": str(item.get("content") or ""),
        }
        for item in items
        if isinstance(item, dict) and item.get("url")
    )
