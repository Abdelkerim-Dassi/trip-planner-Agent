"""Daily usage limits that keep the app inside its free tiers.

Two kinds of counters, both reset at midnight UTC:

- :func:`allow` counts uses per visitor (per IP address), so one person can't
  burn everybody's allowance.
- :func:`spend` counts a global budget, e.g. web searches per day.

Counts live in memory and, when Upstash is configured (see ``storage``), in
Redis as well, so they survive the restarts of a free Render instance. The
larger of the two counts wins. IP addresses are hashed before they are used in
a key; raw addresses are never stored.

Kept free of FastAPI so any module can import it cheaply.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from voyagent import storage

log = logging.getLogger(__name__)

COUNTER_TTL_SECONDS = 2 * 24 * 3600  # a day's counters are useless after that day
_IP_HASH_CHARS = 16


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


# Per visitor, per day. Zero or less means unlimited.
CHECKS_PER_IP = _env_int("VOYAGENT_DAILY_CHECKS_PER_IP", 12)
PLANS_PER_IP = _env_int("VOYAGENT_DAILY_PLANS_PER_IP", 6)
DISCOVERS_PER_IP = _env_int("VOYAGENT_DAILY_DISCOVERS_PER_IP", 12)
# For everybody together, per day.
SEARCH_BUDGET = _env_int("VOYAGENT_DAILY_SEARCH_BUDGET", 200)
MCP_CALLS_BUDGET = _env_int("VOYAGENT_DAILY_MCP_BUDGET", 300)

_counts: dict[str, int] = {}
_counts_day = ""
_lock = threading.Lock()


def client_ip(request: Any) -> str:
    """The visitor's address: the first one in ``X-Forwarded-For`` when the
    app sits behind a proxy (Render), else the socket's peer address."""
    headers = getattr(request, "headers", None) or {}
    forwarded = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For") or ""
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    host = getattr(getattr(request, "client", None), "host", None)
    return host or "unknown"


def allow(kind: str, ip: str, per_day: int) -> bool:
    """Count one use of ``kind`` by ``ip`` today; ``False`` once over ``per_day``."""
    return _use(f"{kind}:{_hash_ip(ip)}", per_day, 1)


def spend(kind: str, per_day: int, amount: int = 1) -> bool:
    """Take ``amount`` from today's global budget for ``kind``; ``False`` when
    that would go over ``per_day``."""
    return _use(kind, per_day, amount)


def _hash_ip(ip: str) -> str:
    return hashlib.sha256((ip or "unknown").encode("utf-8")).hexdigest()[:_IP_HASH_CHARS]


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _use(name: str, per_day: int, amount: int) -> bool:
    global _counts_day
    if per_day <= 0:
        return True
    amount = max(1, int(amount))
    day = _today()
    key = f"{name}:{day}"
    with _lock:
        if day != _counts_day:  # a new day: yesterday's counts are dead weight
            _counts.clear()
            _counts_day = day
        count = _counts.get(key, 0) + amount
        if count > per_day:
            return False  # already known to be over; no need to ask Upstash
        _counts[key] = count

    shared = _shared_count(key, amount)
    if shared is None or shared <= count:
        return True
    # Another process, or this one before a restart, counted more than we know.
    with _lock:
        if _counts_day == day:
            _counts[key] = max(_counts.get(key, 0), shared)
    return shared <= per_day


def _shared_count(key: str, amount: int) -> int | None:
    try:
        return storage.incr(key, COUNTER_TTL_SECONDS, amount)
    except Exception as exc:  # a counter must never break a request
        log.debug("Shared counter unavailable: %s", exc)
        return None
