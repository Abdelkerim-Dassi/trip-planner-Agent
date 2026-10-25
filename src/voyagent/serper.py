"""Plain Serper.dev Google Search client, shared by the agent tool and the
TikTok discovery / MCP tools.

Kept free of ``crewai`` so the web app and MCP server can import it cheaply.
"""

from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict

import requests

SEARCH_URL = "https://google.serper.dev/search"
REQUEST_TIMEOUT_SECONDS = 15
_CACHE_SIZE = 512

_cache: OrderedDict[str, tuple[dict, ...]] = OrderedDict()
_cache_lock = threading.Lock()


class SearchError(RuntimeError):
    """Raised when Serper is unreachable, misconfigured or rejects the query."""


def search(query: str) -> list[dict]:
    """Return Serper's organic results (``title``, ``link``, ``snippet``) for ``query``.

    Results are cached per query for the life of the process, which saves
    credits when several users explore the same destination. Empty answers are
    never cached: Serper occasionally returns nothing for a query that works a
    minute later, and caching that would break the query until a restart.
    """
    query = query.strip()
    with _cache_lock:
        if query in _cache:
            _cache.move_to_end(query)
            return list(_cache[query])

    results = _fetch(query)
    if results:
        with _cache_lock:
            _cache[query] = results
            while len(_cache) > _CACHE_SIZE:
                _cache.popitem(last=False)
    return list(results)


def fresh_search(query: str) -> list[dict]:
    """Like :func:`search` but skips the cache, and replaces the cached answer
    when the fresh one has results."""
    query = query.strip()
    results = _fetch(query)
    if results:
        with _cache_lock:
            _cache[query] = results
    return list(results)


def _fetch(query: str) -> tuple[dict, ...]:
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        raise SearchError("SERPER_API_KEY is not set in the environment.")

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
        except ValueError:
            message = response.text[:200]
        raise SearchError(f"Search failed ({response.status_code}): {message}")

    return tuple(response.json().get("organic") or ())
