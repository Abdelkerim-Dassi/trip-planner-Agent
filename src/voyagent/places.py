"""Place verification with OpenStreetMap's Nominatim geocoder (free, no key).

Every place TripCorrect shows on a map or passes to the agents is checked here
first, so invented or wrong-country places are dropped instead of shown.

Nominatim's usage policy asks for at most one request per second, an
identifying User-Agent, and caching — all three are enforced below.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, fields

import requests

from voyagent import storage

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = os.environ.get(
    "VOYAGENT_USER_AGENT", "TripCorrect/0.3 (open-source AI trip planner)"
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
#: A match this close to the destination city counts as "in or around it".
NEAR_KM = 60
_IN_TOWN_KM = 15
#: Half-width, in degrees, of the box around a city in which matches are preferred.
_BIAS_DEGREES = 0.5
#: A "not found" answer is asked again after a week: the map gets updated.
_NOT_FOUND_TTL_SECONDS = 7 * 24 * 3600
_FOUND_TTL_SECONDS = 90 * 24 * 3600

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
    opening_hours: str = ""  # OSM opening_hours tag, when mapped
    locality: str = ""  # the town or city it is in, e.g. "Sidi Bou Said"

    @property
    def is_city(self) -> bool:
        return self.kind in _CITY_TYPES

    def to_dict(self) -> dict:
        return asdict(self)


def _throttled_get(params: dict) -> list[dict] | None:
    """GET Nominatim, spacing requests at least ~1s apart across all threads.

    Returns ``None`` when the request itself failed, so callers don't mistake
    an outage for "this place doesn't exist".
    """
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
                    "extratags": 1,
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
            return None
        finally:
            _last_request = time.monotonic()


def _locality(address: dict) -> str:
    """The town a place is in. Small towns often have no name in the requested
    language; a larger area that does ("Mahdia") reads better than Arabic
    script in an English report."""
    names = [
        address[key]
        for key in ("city", "town", "village", "municipality", "suburb", "county",
                    "state_district", "state")
        if address.get(key)
    ]
    if LANGUAGE not in ("ar", "fa", "he"):
        readable = [n for n in names if sum(c.isascii() for c in n) >= len(n) * 0.6]
        if readable:
            return readable[0]
    return names[0] if names else ""


def _to_place(hit: dict, query: str) -> Place:
    address = hit.get("address") or {}
    return Place(
        name=hit.get("name") or query,
        display_name=hit.get("display_name", query),
        lat=float(hit["lat"]),
        lon=float(hit["lon"]),
        country_code=address.get("country_code", ""),
        kind=hit.get("addresstype") or hit.get("type", ""),
        osm_url=f"https://www.openstreetmap.org/{hit.get('osm_type')}/{hit.get('osm_id')}",
        category=hit.get("category", ""),
        osm_type=hit.get("type", ""),
        opening_hours=(hit.get("extratags") or {}).get("opening_hours", ""),
        locality=_locality(address),
    )


_PLACE_FIELDS = {f.name for f in fields(Place)}
_memory: dict[str, Place | None] = {}
_memory_lock = threading.Lock()


def _cache_key(query: str, country_code: str, near: tuple[float, float] | None) -> str:
    raw = f"{query.strip().lower()}|{country_code.lower()}|{near or ''}|{LANGUAGE}"
    return hashlib.sha1(raw.encode()).hexdigest()[:32]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def geocode(
    query: str, country_code: str = "", near: tuple[float, float] | None = None
) -> Place | None:
    """Find ``query`` on OpenStreetMap, optionally restricted to one country.

    ``near`` is a (lat, lon) to prefer: "Medina" near Tunis should be the
    Medina of Tunis, not the first "Medina" in the country. The best match
    within :data:`NEAR_KM` wins; failing that, the top match anywhere.

    Returns ``None`` when nothing matches — callers treat that as "unverified".
    Answers are cached in memory and in storage, so a popular place is looked
    up once, not once per visitor.
    """
    key = _cache_key(query, country_code, near)
    with _memory_lock:
        if key in _memory:
            return _memory[key]
    cached = storage.load("geo", key)
    if cached:
        data = cached.get("place")
        fresh = time.time() - cached.get("t", 0) < _NOT_FOUND_TTL_SECONDS
        if data or fresh:
            place = Place(**{k: v for k, v in data.items() if k in _PLACE_FIELDS}) if data else None
            with _memory_lock:
                _memory[key] = place
            return place

    params: dict = {"q": query}
    if country_code:
        params["countrycodes"] = country_code.lower()
    if near:
        lat, lon = near
        d = _BIAS_DEGREES
        params.update(viewbox=f"{lon - d},{lat + d},{lon + d},{lat - d}", limit=5)
    results = _throttled_get(params)
    if results is None:
        return None  # request failed: say "unverified" now, ask again next time
    place = None
    if results:
        hit = results[0]
        if near:
            # In the city itself first, then around it, then anywhere: a bare
            # "Médina" near Tunis is Tunis's, not the next town's.
            km = [_haversine(near[0], near[1], float(r["lat"]), float(r["lon"])) for r in results]
            for limit in (_IN_TOWN_KM, NEAR_KM):
                close = [r for r, d in zip(results, km) if d <= limit]
                if close:
                    hit = close[0]
                    break
        place = _to_place(hit, query)
    with _memory_lock:
        _memory[key] = place
    storage.save(
        "geo",
        key,
        {"t": time.time(), "place": place.to_dict() if place else None},
        _FOUND_TTL_SECONDS if place else _NOT_FOUND_TTL_SECONDS,
    )
    return place


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

    When ``near`` is a city, matches in and around it are preferred, and a
    match far from it is retried as "name, near" (helps with generic names
    like "Old Medina"). Failing that, it retries without generic words such
    as "Oasis" or "Rocks"; a shortened name is ambiguous ("Chebika" is also a
    district elsewhere), so those matches must not be administrative areas
    and, near a city, must lie within ``_FALLBACK_MAX_KM`` of it.

    A place found far from ``near`` is still returned: the caller decides
    what the distance means (a day trip, or a place in the wrong city).
    """
    anchor = geocode(near) if near else None
    country = anchor.country_code if anchor else ""
    bias = (round(anchor.lat, 2), round(anchor.lon, 2)) if anchor and anchor.is_city else None
    place = geocode(name, country, bias)
    if near and (place is None or (bias and distance_km(anchor, place) > NEAR_KM)):
        closer = geocode(f"{name}, {near}", country, bias)
        if closer is not None and (
            place is None or (bias and distance_km(anchor, closer) <= NEAR_KM)
        ):
            place = closer
    if place is not None:
        return place

    core = _core_name(name)
    if not core:
        return None
    for query in ([f"{core}, {near}"] if near else []) + [core]:
        place = geocode(query, country, bias)
        if place is None or place.kind in _ADMIN_KINDS:
            continue
        if anchor and anchor.is_city and distance_km(anchor, place) > _FALLBACK_MAX_KM:
            continue
        return place
    return None


def distance_km(a: Place, b: Place) -> float:
    """Great-circle distance between two places, in kilometres."""
    return _haversine(a.lat, a.lon, b.lat, b.lon)
