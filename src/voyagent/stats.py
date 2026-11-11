"""Usage counts without a third-party tracker: no cookies, no visitor ids.

Each event (a visit, a check started, a plan finished, a thumbs-up) adds one
to a per-day counter. Counts live in memory and, when Upstash is configured,
in Redis for 120 days, so they survive the restarts of a free host. Nothing
about the visitor is recorded. The ``/stats`` page reads them back.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from voyagent import storage

TTL_SECONDS = 120 * 24 * 3600
#: Shown on /stats, in this order.
EVENTS = [
    ("visit", "Home page visits"),
    ("check_started", "Checks started"),
    ("check_done", "Checks finished"),
    ("fix_started", "Fixes requested"),
    ("report_view", "Shared report views"),
    ("discover", "TikTok discoveries"),
    ("plan_started", "Plans started"),
    ("plan_done", "Plans finished"),
    ("plan_view", "Shared plan views"),
    ("mcp_check", "Checks from assistants (MCP)"),
    ("feedback_up", "Thumbs up"),
    ("feedback_down", "Thumbs down"),
]
_NAMES = {name for name, _ in EVENTS}

_memory: dict[str, int] = {}
_lock = threading.Lock()


def _day(offset: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y%m%d")


def hit(event: str) -> None:
    """Count one ``event`` for today. Never raises: stats must not break a request."""
    if event not in _NAMES:
        return
    key = f"stat.{event}.{_day()}"
    with _lock:
        _memory[key] = _memory.get(key, 0) + 1
    try:
        storage.incr(key, TTL_SECONDS)
    except Exception:  # an outage of the counter store is not the visitor's problem
        pass


def read(days: int = 14) -> dict:
    """``{"days": ["2026-11-11", ...], "rows": [{"label", "counts": [...], "total"}]}``,
    newest day first."""
    stamps = [_day(offset) for offset in range(days)]
    rows = []
    for event, label in EVENTS:
        counts = []
        for stamp in stamps:
            key = f"stat.{event}.{stamp}"
            remote = storage.count(key)
            with _lock:
                local = _memory.get(key, 0)
            counts.append(max(remote or 0, local))
        rows.append({"label": label, "counts": counts, "total": sum(counts)})
    return {
        "days": [f"{s[:4]}-{s[4:6]}-{s[6:]}" for s in stamps],
        "rows": rows,
        "persisted": storage.is_remote(),
    }
