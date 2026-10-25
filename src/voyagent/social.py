"""Turn what travellers share on TikTok into verified trip ideas.

Two entry points:

- :func:`trending_spots` — "what does TikTok love in Tunisia in December?"
  Searches Google's index of TikTok videos (through Serper), so ReelTrip never
  scrapes TikTok or downloads videos.
- :func:`spots_from_links` — the user pastes TikTok links they saved; each is
  looked up the same way to read its caption.

Both feed the captions to the LLM to pull out the places they mention, then
keep only the places OpenStreetMap confirms (in the destination's country),
ranked by how many videos mention them. Every spot links back to its videos.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from voyagent import config
from voyagent.places import Place, distance_km, geocode, verify_place
from voyagent.serper import SearchError, search

MAX_LINKS = 10
MAX_SPOTS = 10
_TIKTOK_HOSTS = ("tiktok.com",)
_VIDEO_ID = re.compile(r"/video/(\d+)")
# Geocoding "Sahara" can land on the "Sahara Beach Hotel". When the captions
# describe an area or landscape, reject matches that are a single business.
_AREA_KINDS = {"town", "island", "nature", "beach", "region"}
_BUSINESS_CATEGORIES = {"amenity", "shop", "tourism", "building", "office", "craft"}
_ATTRACTION_TYPES = {"attraction", "viewpoint", "museum", "artwork", "theme_park"}


def _plausible(kind: str, place: Place) -> bool:
    if kind not in _AREA_KINDS:
        return True
    return place.category not in _BUSINESS_CATEGORIES or place.osm_type in _ATTRACTION_TYPES


@dataclass
class Video:
    url: str
    title: str
    caption: str
    author: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}. {self.caption}".strip(". ")


@dataclass
class Spot:
    name: str
    kind: str
    why: str
    mentions: int
    videos: list[str]
    lat: float | None = None
    lon: float | None = None
    address: str = ""
    osm_url: str = ""
    #: Straight-line distance from the destination, when it is a city.
    distance_km: float | None = None
    verified: bool = False


@dataclass
class Discovery:
    destination: str
    videos: list[Video] = field(default_factory=list)
    spots: list[Spot] = field(default_factory=list)
    #: Places the captions mention that OpenStreetMap could not confirm.
    unverified: list[str] = field(default_factory=list)
    center: dict | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_brief(self) -> str:
        """Markdown summary handed to the planning crew as inspiration."""
        if not self.spots:
            return ""
        lines = [f"Places travellers rave about on TikTok for {self.destination}:"]
        for spot in self.spots:
            where = f" (~{spot.distance_km:.0f} km away)" if spot.distance_km else ""
            lines.append(
                f"- {spot.name}{where}: {spot.why} "
                f"[mentioned in {spot.mentions} video(s)]"
            )
        return "\n".join(lines)


def _author(url: str) -> str:
    match = re.search(r"tiktok\.com/(@[^/?#]+)", url)
    return match.group(1) if match else ""


def _is_tiktok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _TIKTOK_HOSTS)


def _videos_from_results(results: list[dict]) -> list[Video]:
    videos = []
    for result in results:
        link = result.get("link", "")
        if not _is_tiktok(link):
            continue
        title = re.sub(r"\s*\|\s*TikTok\s*$", "", result.get("title", ""))
        videos.append(
            Video(url=link, title=title, caption=result.get("snippet", ""), author=_author(link))
        )
    return videos


def _search_queries(destination: str, month: str, interests: str) -> list[str]:
    base = f"site:tiktok.com {destination}"
    queries = [f"{base} places to visit", f"{base} hidden gems"]
    if month:
        queries.append(f"{base} in {month}")
    if interests:
        queries.append(f"{base} {interests}")
    return queries[:3]


def _extract_places(videos: list[Video], destination: str) -> list[dict]:
    """Ask the LLM which concrete places the captions mention."""
    import litellm  # ships with crewai; imported lazily to keep startup fast

    numbered = "\n".join(f"[{i}] {v.text[:400]}" for i, v in enumerate(videos))
    prompt = f"""
You read TikTok video captions about travel to {destination or "a destination"}.
List the specific, named places and experiences they recommend: towns, sights,
beaches, markets, neighbourhoods, restaurants, natural sites.

Rules:
- Only places explicitly named in the captions. Never add places yourself.
- Skip generic words ("the beach", "local cafes") and anything outside
  {destination or "the destination"}'s country.
- Merge spelling variants into one entry with the most common name.
- "why" is one short sentence based only on what the captions say.
- "videos" lists the [numbers] of every caption that mentions the place.

Return JSON only: {{"places": [{{"name": "...", "kind": "town|sight|beach|nature|food|market|experience",
"why": "...", "videos": [0, 2]}}]}}

Captions:
{numbered}
""".strip()
    response = litellm.completion(
        model=config.litellm_model(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
        num_retries=3,
    )
    content = response.choices[0].message.content or "{}"
    try:
        places = json.loads(content).get("places", [])
    except (ValueError, AttributeError):
        return []
    return [p for p in places if isinstance(p, dict) and p.get("name")]


def _build(destination: str, videos: list[Video], max_spots: int) -> Discovery:
    discovery = Discovery(destination=destination, videos=videos)
    if not videos:
        discovery.notes.append("No TikTok videos found for this search.")
        return discovery

    anchor: Place | None = geocode(destination) if destination else None
    if anchor:
        discovery.center = {"lat": anchor.lat, "lon": anchor.lon, "name": anchor.name}

    candidates = _extract_places(videos, destination)
    # Rank by how many distinct videos mention the place, then verify the top
    # ones (verification is rate-limited to ~1 lookup per second).
    candidates.sort(key=lambda p: len(set(p.get("videos") or [])), reverse=True)

    for candidate in candidates:
        if len(discovery.spots) >= max_spots:
            break
        indices = sorted({i for i in candidate.get("videos") or [] if isinstance(i, int)})
        urls = [videos[i].url for i in indices if 0 <= i < len(videos)]
        place = verify_place(candidate["name"], destination)
        if (
            place is None
            or (anchor and place.country_code != anchor.country_code)
            or not _plausible(candidate.get("kind", ""), place)
        ):
            discovery.unverified.append(candidate["name"])
            continue
        if place.kind == "country" or (anchor and place.osm_url == anchor.osm_url):
            continue  # the destination itself ("Tunisia", "Tunis") is not a spot
        discovery.spots.append(
            Spot(
                name=candidate["name"],
                kind=candidate.get("kind", ""),
                why=candidate.get("why", ""),
                mentions=max(len(urls), 1),
                videos=urls,
                lat=place.lat,
                lon=place.lon,
                address=place.display_name,
                osm_url=place.osm_url,
                distance_km=(
                    round(distance_km(anchor, place), 1)
                    if anchor and anchor.is_city
                    else None
                ),
                verified=True,
            )
        )
    return discovery


def trending_spots(
    destination: str, month: str = "", interests: str = "", max_spots: int = MAX_SPOTS
) -> Discovery:
    """Find the places TikTok travellers recommend for ``destination``."""
    videos: dict[str, Video] = {}
    for query in _search_queries(destination.strip(), month.strip(), interests.strip()):
        try:
            for video in _videos_from_results(search(query)):
                videos.setdefault(video.url, video)
        except SearchError as exc:
            discovery = Discovery(destination=destination)
            discovery.notes.append(str(exc))
            return discovery
    return _build(destination.strip(), list(videos.values()), max_spots)


def spots_from_links(
    links: list[str], destination: str = "", max_spots: int = MAX_SPOTS
) -> Discovery:
    """Read the captions of TikTok links the user saved and map their places.

    Each link is looked up in Google's index (TikTok's own embed API no longer
    returns captions). Links Google hasn't indexed are reported in ``notes``.
    """
    videos, missed = [], []
    for link in [l.strip() for l in links if l.strip()][:MAX_LINKS]:
        if not _is_tiktok(link):
            missed.append(f"Not a TikTok link: {link}")
            continue
        video_id = _VIDEO_ID.search(link)
        try:
            results = search(link)
        except SearchError as exc:
            missed.append(str(exc))
            break
        match = next(
            (
                r
                for r in results
                if video_id and video_id.group(1) in r.get("link", "")
                or r.get("link", "").rstrip("/") == link.rstrip("/")
            ),
            None,
        )
        if match is None:
            missed.append(f"Couldn't read this video's caption yet: {link}")
            continue
        videos.extend(_videos_from_results([match]))

    discovery = _build(destination.strip(), videos, max_spots)
    discovery.notes.extend(missed)
    return discovery
