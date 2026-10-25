"""Place verification with OpenStreetMap's Nominatim geocoder (free, no key).

Every place ReelTrip shows on a map or passes to the agents is checked here
first, so invented or wrong-country places are dropped instead of shown.

Nominatim's usage policy asks for at most one request per second, an
identifying User-Agent, and caching — all three are enforced below.
"""

from __future__ import annotations

import math
import os
import re
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

# Landform words travellers add to names that OSM usually leaves out.
_GENERIC_WORDS = {
    "oasis", "rocks", "rock", "beach", "beaches", "village", "island", "lake",
    "canyon", "gorge", "waterfall", "waterfalls", "dunes", "ruins", "viewpoint",
}
# Region-level results a shortened name must not resolve to.
_ADMIN_KINDS = {"state", "state_district", "county", "region", "province", "country"}
#: How far from the destination city a shortened-name match may be.
_FALLBACK_MAX_KM = 150

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


def _core_name(name: str) -> str:
    """Drop generic landform words that OpenStreetMap names often omit.

    Travellers write "Chebika Oasis" or "Belvedere Rocks"; OSM has "Chebika".
    Returns "" when nothing specific would be left.
    """
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    core = [w for w in words if w.lower().strip(",.") not in _GENERIC_WORDS]
    return " ".join(core) if core and len(core) < len(words) else ""


def verify_place(name: str, near: str = "") -> Place | None:
    """Check that ``name`` is a real place, inside ``near``'s country if given.

    Tries the bare name first (restricted to the country), then "name, near"
    (helps with generic names like "Old Medina"). Failing that, it retries
    without generic words such as "Oasis" or "Rocks"; a shortened name is
    ambiguous ("Chebika" is also a district elsewhere), so those matches must
    not be administrative areas and, near a city, must lie within
    ``_FALLBACK_MAX_KM`` of it.
    """
    anchor = geocode(near) if near else None
    country = anchor.country_code if anchor else ""
    place = geocode(name, country)
    if place is None and near:
        place = geocode(f"{name}, {near}", country)
    if place is not None:
        return place

    core = _core_name(name)
    if not core:
        return None
    for query in ([f"{core}, {near}"] if near else []) + [core]:
        place = geocode(query, country)
        if place is None or place.kind in _ADMIN_KINDS:
            continue
        if anchor and anchor.is_city and distance_km(anchor, place) > _FALLBACK_MAX_KM:
            continue
        return place
    return None


def distance_km(a: Place, b: Place) -> float:
    """Great-circle distance between two places, in kilometres."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(h))
