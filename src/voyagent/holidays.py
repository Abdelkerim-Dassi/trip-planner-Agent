"""Public holidays for a country, from the free Nager.Date API (no key).

Sights and shops often close or keep short hours on a public holiday, and a
trip plan rarely knows the day is one. The list is whatever Nager.Date
publishes: nationwide holidays with fixed or computed dates. Holidays set by
moon sighting (Eid) are missing for many countries, so an empty answer is
"none known", not "none".
"""

from __future__ import annotations

import logging
import threading
import time

import requests

from voyagent import storage

log = logging.getLogger(__name__)

API_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
REQUEST_TIMEOUT_SECONDS = 8
CACHE_TTL_SECONDS = 30 * 24 * 3600

_memory: dict[str, dict[str, str]] = {}
_lock = threading.Lock()


def public_holidays(country_code: str, year: int) -> dict[str, str]:
    """``{"2026-12-25": "Christmas Day", ...}`` for nationwide holidays.

    Empty when the country isn't covered or the service can't be reached.
    """
    country = (country_code or "").upper()
    if len(country) != 2 or not country.isalpha():
        return {}
    key = f"{country.lower()}{int(year)}"
    with _lock:
        if key in _memory:
            return _memory[key]
    cached = storage.load("holidays", key)
    if cached and time.time() - cached.get("t", 0) < CACHE_TTL_SECONDS:
        days = cached.get("days", {})
    else:
        try:
            response = requests.get(
                API_URL.format(year=int(year), country=country), timeout=REQUEST_TIMEOUT_SECONDS
            )
            if response.status_code == 404:  # country not covered
                entries = []
            else:
                response.raise_for_status()
                entries = response.json()
        except (requests.RequestException, ValueError) as exc:
            log.info("Holiday lookup unavailable: %s", type(exc).__name__)
            return {}  # not cached: ask again next time
        days = {
            e["date"]: e.get("name") or e.get("localName") or "Public holiday"
            for e in entries
            if isinstance(e, dict) and e.get("date") and e.get("global", True)
        }
        storage.save("holidays", key, {"t": time.time(), "days": days}, CACHE_TTL_SECONDS)
    with _lock:
        _memory[key] = days
    return days
