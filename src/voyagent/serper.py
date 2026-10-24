"""Plain Serper.dev Google Search client, shared by the agent tool and the
TikTok discovery / MCP tools.

Kept free of ``crewai`` so the web app and MCP server can import it cheaply.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

import requests

SEARCH_URL = "https://google.serper.dev/search"
REQUEST_TIMEOUT_SECONDS = 15


class SearchError(RuntimeError):
    """Raised when Serper is unreachable, misconfigured or rejects the query."""


def search(query: str) -> list[dict]:
    """Return Serper's organic results (``title``, ``link``, ``snippet``) for ``query``.

    Results are cached per query for the life of the process, which saves
    credits when several users explore the same destination.
    """
    return list(_cached_search(query.strip()))


@lru_cache(maxsize=512)
def _cached_search(query: str) -> tuple[dict, ...]:
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
