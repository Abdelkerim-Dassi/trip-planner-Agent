"""Road distance and driving time between a day's stops.

A straight line says little about a day on the road: Tunis, Kairouan, El Jem
and Sousse are about 130 km apart as the crow flies and more than four hours
of driving. This asks OSRM (the open routing engine built on OpenStreetMap)
for the real figure.

The default server is OSRM's public demo instance: free, no key, meant for
light use, with no guarantee it is up. So every answer is cached, at most one
request is made per day of an itinerary, and any failure falls back silently
to the straight-line figure. Point ``VOYAGENT_ROUTING_URL`` at another OSRM
server to change it, or set it to "" to turn routing off.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading

import requests

from voyagent import storage
from voyagent.places import USER_AGENT

log = logging.getLogger(__name__)

ROUTING_URL = os.environ.get("VOYAGENT_ROUTING_URL", "https://router.project-osrm.org").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 8
CACHE_TTL_SECONDS = 180 * 24 * 3600
#: OSRM accepts long routes, but a day never needs more than this.
MAX_POINTS = 12

_memory: dict[str, dict] = {}
_lock = threading.Lock()


def drive(points: list[tuple[float, float]]) -> dict | None:
    """Road ``{"km", "minutes"}`` through ``points`` (lat, lon) in order.

    ``None`` when routing is off, there are fewer than two points, or the
    server can't answer; callers then keep their straight-line estimate.
    """
    points = points[:MAX_POINTS]
    if not ROUTING_URL or len(points) < 2:
        return None
    path = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in points)
    key = hashlib.sha1(path.encode()).hexdigest()[:32]
    with _lock:
        if key in _memory:
            return _memory[key]
    cached = storage.load("route", key)
    if cached and "km" in cached:
        with _lock:
            _memory[key] = cached
        return cached
    try:
        response = requests.get(
            f"{ROUTING_URL}/route/v1/driving/{path}",
            params={"overview": "false"},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        route = response.json()["routes"][0]
        result = {"km": round(route["distance"] / 1000), "minutes": round(route["duration"] / 60)}
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        log.info("Routing unavailable: %s", type(exc).__name__)
        return None
    with _lock:
        _memory[key] = result
    storage.save("route", key, result, CACHE_TTL_SECONDS)
    return result


def hours_minutes(minutes: int) -> str:
    """75 -> "1 h 15 min"; 40 -> "40 min"."""
    hours, rest = divmod(int(minutes), 60)
    if not hours:
        return f"{rest} min"
    return f"{hours} h {rest:02d} min" if rest else f"{hours} h"
