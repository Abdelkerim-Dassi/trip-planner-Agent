"""Place verification with OpenStreetMap's Nominatim geocoder (free, no key).

Every place ReelTrip shows on a map or passes to the agents is checked here
first, so invented or wrong-country places are dropped instead of shown.

Nominatim's usage policy asks for at most one request per second, an
identifying User-Agent, and caching — all three are enforced below.
"""

from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import asdict, dataclass
from functools import lru_cache

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = os.environ.get(
    "VOYAGENT_USER_AGENT", "ReelTrip/0.2 (open-source AI trip planner)"
)
#: Language for returned names/addresses (Nominatim otherwise uses local script).
LANGUAGE = os.environ.get("VOYAGENT_LANGUAGE", "en")
REQUEST_TIMEOUT_SECONDS = 15
_MIN_INTERVAL_SECONDS = 1.1

# Address types that describe a city-sized place, where "distance from the
# destination" is meaningful. For a country or region it is not.
_CITY_TYPES = {"city", "town", "village", "municipality", "suburb", "hamlet"}

_lock = threading.Lock()
_last_request = 0.0


@dataclass(frozen=True)
class Place:
    name: str
    display_name: str
    lat: float
    lon: float
    country_code: str
    kind: str  # Nominatim addresstype, e.g. "city", "country", "attraction"
    osm_url: str
    category: str = ""  # OSM key, e.g. "place", "natural", "tourism", "amenity"
    osm_type: str = ""  # OSM value, e.g. "town", "beach", "hotel", "museum"

    @property
    def is_city(self) -> bool:
        return self.kind in _CITY_TYPES

    def to_dict(self) -> dict:
        return asdict(self)


def _throttled_get(params: dict) -> list[dict]:
    """GET Nominatim, spacing requests at least ~1s apart across all threads."""
    global _last_request
    with _lock:
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            response = requests.get(
                NOMINATIM_URL,
                params={
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": 1,
                    "accept-language": LANGUAGE,
                    **params,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return []
        finally:
            _last_request = time.monotonic()


@lru_cache(maxsize=2048)
def geocode(query: str, country_code: str = "") -> Place | None:
    """Find ``query`` on OpenStreetMap, optionally restricted to one country.

    Returns ``None`` when nothing matches — callers treat that as "unverified".
    """
    params = {"q": query}
    if country_code:
        params["countrycodes"] = country_code.lower()
    results = _throttled_get(params)
    if not results:
        return None
    hit = results[0]
    return Place(
        name=hit.get("name") or query,
        display_name=hit.get("display_name", query),
        lat=float(hit["lat"]),
        lon=float(hit["lon"]),
        country_code=(hit.get("address") or {}).get("country_code", ""),
        kind=hit.get("addresstype") or hit.get("type", ""),
        osm_url=f"https://www.openstreetmap.org/{hit.get('osm_type')}/{hit.get('osm_id')}",
        category=hit.get("category", ""),
        osm_type=hit.get("type", ""),
    )


def verify_place(name: str, near: str = "") -> Place | None:
    """Check that ``name`` is a real place, inside ``near``'s country if given.

    Tries the bare name first (restricted to the country), then "name, near",
    which helps with generic names like "Old Medina".
    """
    country = ""
    if near:
        anchor = geocode(near)
        country = anchor.country_code if anchor else ""
    place = geocode(name, country)
    if place is None and near:
        place = geocode(f"{name}, {near}", country)
    return place


def distance_km(a: Place, b: Place) -> float:
    """Great-circle distance between two places, in kilometres."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(h))
