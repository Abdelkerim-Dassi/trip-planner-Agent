"""Small grounded lookups a trip planner needs: typical weather for a month,
daily prayer times, and how to get between two places.

All sources are free and need no API key except transfers, which reuse the
Serper search key. Each function returns plain dicts so the web API and the
MCP server can hand them straight to clients.
"""

from __future__ import annotations

import calendar
from datetime import date
from functools import lru_cache
from statistics import mean

import requests

from voyagent.places import distance_km, geocode
from voyagent.serper import SearchError, search

REQUEST_TIMEOUT_SECONDS = 20
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
ALADHAN_TIMINGS = "https://api.aladhan.com/v1/timings/{day}"
_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})


class LookupError_(RuntimeError):
    """A lookup failed in a way worth telling the traveller about."""


def _month_number(month: str | int) -> int:
    if isinstance(month, int) or str(month).isdigit():
        number = int(month)
    else:
        number = _MONTHS.get(str(month).strip().lower(), 0)
    if not 1 <= number <= 12:
        raise LookupError_(f"Unknown month: {month!r}. Use a name like 'December'.")
    return number


def _place(name: str):
    place = geocode(name)
    if place is None:
        raise LookupError_(f"Couldn't find {name!r} on OpenStreetMap.")
    return place


@lru_cache(maxsize=256)
def typical_weather(place: str, month: str) -> dict:
    """Typical conditions for ``month`` at ``place``, from last year's records.

    Uses the most recent complete occurrence of that month (Open-Meteo's
    historical archive), which is far more honest than a model guessing.
    """
    number = _month_number(month)
    loc = _place(place)
    today = date.today()
    year = today.year if number < today.month else today.year - 1
    last_day = calendar.monthrange(year, number)[1]
    try:
        response = requests.get(
            OPEN_METEO_ARCHIVE,
            params={
                "latitude": loc.lat,
                "longitude": loc.lon,
                "start_date": f"{year}-{number:02d}-01",
                "end_date": f"{year}-{number:02d}-{last_day}",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": "auto",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        daily = response.json()["daily"]
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise LookupError_(f"Weather lookup failed: {exc}") from exc

    highs = [t for t in daily["temperature_2m_max"] if t is not None]
    lows = [t for t in daily["temperature_2m_min"] if t is not None]
    rain = [r for r in daily["precipitation_sum"] if r is not None]
    return {
        "place": loc.display_name,
        "month": calendar.month_name[number],
        "based_on_year": year,
        "avg_high_c": round(mean(highs), 1),
        "avg_low_c": round(mean(lows), 1),
        "coldest_night_c": round(min(lows), 1),
        "hottest_day_c": round(max(highs), 1),
        "rainy_days": sum(1 for r in rain if r >= 1.0),
        "total_rain_mm": round(sum(rain), 1),
        "source": "Open-Meteo historical weather (open-meteo.com)",
    }


@lru_cache(maxsize=512)
def prayer_times(place: str, day: str = "") -> dict:
    """Islamic prayer times at ``place`` on ``day`` (YYYY-MM-DD, default today).

    AlAdhan picks the calculation method used locally for those coordinates.
    """
    loc = _place(place)
    when = date.fromisoformat(day) if day else date.today()
    try:
        response = requests.get(
            ALADHAN_TIMINGS.format(day=when.strftime("%d-%m-%Y")),
            params={"latitude": loc.lat, "longitude": loc.lon},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()["data"]
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise LookupError_(f"Prayer-time lookup failed: {exc}") from exc

    keep = ("Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha")
    return {
        "place": loc.display_name,
        "date": when.isoformat(),
        "times": {k: data["timings"][k] for k in keep},
        "hijri_date": data["date"]["hijri"]["date"],
        "method": data["meta"]["method"]["name"],
        "source": "AlAdhan prayer times API (aladhan.com)",
    }


def transfer_options(origin: str, destination: str) -> dict:
    """How travellers get from ``origin`` to ``destination``.

    Returns the straight-line distance plus the top web results about trains,
    buses, shared taxis and flights, so the caller can summarise real options
    with their sources rather than inventing schedules.
    """
    a, b = _place(origin), _place(destination)
    try:
        results = search(f"{origin} to {destination} train bus louage taxi how to get duration price")
    except SearchError as exc:
        raise LookupError_(str(exc)) from exc
    return {
        "origin": a.display_name,
        "destination": b.display_name,
        "straight_line_km": round(distance_km(a, b)),
        "sources": [
            {"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
            for r in results[:5]
        ],
        "note": "Road distance is usually 20-40% longer than the straight line.",
    }
