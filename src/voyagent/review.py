"""Itinerary check: read any trip plan and test it against the real world.

The plan can come from anywhere: ChatGPT, Gemini, a blog, a friend, or
ReelTrip's own planner. One small model call lists the places it names, day by
day. Everything after that is looked up, not generated:

1. every place is searched on OpenStreetMap, near the town that day is set in;
2. a place found far from that town is flagged (wrong place, or a long detour);
3. sights get their weekly closing days (OpenStreetMap, or published hours
   found by search), and a visit on a closed weekday is flagged;
4. the straight-line distance a day covers and the number of sights in it are
   measured against what a day can hold.

The result says what was checked and what was not, in counts, so the page
never claims more than the check did.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from textwrap import dedent
from typing import Callable

from voyagent import config, holidays, hours, routes, storage
from voyagent.llm import complete, complete_json
from voyagent.places import NEAR_KM, Place, distance_km, geocode, verify_place
from voyagent.plan_text import split_days
from voyagent.serper import SearchError, search
from voyagent.travel_info import parse_date_range, ramadan_days

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 14000
MAX_STOPS = 28
MAX_STOPS_PER_DAY = 8
MAX_DAYS = 21
#: Sights whose closing days are looked up (each may cost a search credit).
MAX_HOURS_LOOKUPS = 8
#: Places missing from the map that are then looked for on the web (one
#: search each), to tell "real but unmapped" from "no trace anywhere".
MAX_WEB_LOOKUPS = 5
#: A place this far from the day's town is a detour or the wrong place.
FAR_KM = NEAR_KM
#: Straight-line kilometres between a day's stops before the day is "long"
#: (used when the routing server can't give a driving time).
LONG_DAY_KM = 120
#: Days whose stops are at least this far apart get a real driving time.
ROUTE_FROM_KM = 30
#: Minutes of driving in one day before the day is "long".
LONG_DRIVE_MINUTES = 120
#: Sights in one day before the day is "packed".
PACKED_SIGHTS = 6

_KINDS = {"sight", "food", "area", "stay"}
_MOSQUE = re.compile(r"mosque|mosquée|mosquee|masjid|camii|جامع|مسجد", re.IGNORECASE)
#: Countries where Ramadan changes opening hours and daytime dining.
_RAMADAN_COUNTRIES = {
    "ma", "dz", "tn", "ly", "eg", "sd", "mr", "sa", "ae", "qa", "kw", "bh", "om", "ye",
    "jo", "ps", "sy", "iq", "ir", "tr", "az", "uz", "tm", "tj", "kg", "kz", "af", "pk",
    "bd", "mv", "id", "my", "bn", "sn", "ml", "ne", "gm", "gn", "so", "dj", "km", "lb",
}
# What a restaurant or a sight can't be: a "Dar Zarrouk" that turns out to be
# a wine shop is a different business with the same name.
_NOT_FOOD = {"highway", "boundary", "place", "natural", "waterway", "landuse", "railway", "office"}
_FOOD_SHOPS = {"bakery", "pastry", "confectionery", "coffee", "tea", "deli", "ice_cream"}
_NOT_SIGHT = {"shop", "office", "craft"}

# Sights known for timed tickets that sell out: a visit planned without a
# booking often doesn't happen. Matched on accent-free lower-case names. Kept
# short on purpose: only places where "book ahead" is long-standing advice.
_BOOK_AHEAD = (
    "alhambra", "nasrid", "sagrada familia", "park guell", "casa batllo", "last supper",
    "cenacolo", "santa maria delle grazie", "anne frank", "vatican museums", "sistine chapel",
    "colosseum", "colosseo", "uffizi", "accademia gallery", "galleria dell accademia",
    "eiffel tower", "tour eiffel", "louvre", "neuschwanstein", "machu picchu", "burj khalifa",
    "ghibli museum", "teamlab", "statue of liberty", "jardin majorelle", "majorelle garden",
    "van gogh museum", "borghese",
)

# Progress callback: (done, total, label of the place being checked).
Progress = Callable[[int, int, str], None]


class ReviewError(RuntimeError):
    """The text couldn't be read as an itinerary; the message is for the user."""


@dataclass
class Stop:
    day: int
    name: str
    kind: str = "sight"
    city: str = ""
    # found: on the map near the day's town   far: on the map, far from it
    # web: not on the map, but the web knows it   no_trace: neither
    # not_found: not on the map (web not searched)
    status: str = "unchecked"
    web_source: str = ""  # a page that mentions it, when status is "web"
    lat: float | None = None
    lon: float | None = None
    osm_url: str = ""
    where: str = ""  # the town the map puts it in
    distance_km: int | None = None  # from the day's town
    hours: str = ""
    closed_days: list[str] = field(default_factory=list)
    hours_source: str = ""
    hours_status: str = ""  # ok | unverified | "" (not looked up)
    local_name: str = ""  # the name used locally, tried when the first isn't found
    moved_from: int | None = None  # the day it was on before a closed-day fix


@dataclass
class Issue:
    level: str  # problem | warning | note
    kind: str
    title: str
    detail: str = ""
    day: int | None = None
    stop: str = ""
    source: str = ""


# --- Reading the itinerary -------------------------------------------------------


def _extract(text: str, destination: str) -> dict:
    hint = f"The trip is to {destination}." if destination else ""
    prompt = dedent(
        f"""
        Below is a trip itinerary. {hint} List the specific, named places it
        sends the traveller to, day by day, in the order they are visited.

        Rules:
        - "name": copy each place name EXACTLY as written (keep its language).
        - "local": the name the place goes by locally, in the local language,
          if you know it and it differs (e.g. "Bassins des Aghlabides" for
          "Aghlabid Basins"); otherwise "".
        - Only specific named places: a museum, monument, site, market, park,
          neighbourhood, town, restaurant, café, hotel. Skip generic ones ("a
          local café", "the hotel", "the beach") and skip airports, stations
          and transport.
        - Skip places mentioned only as an alternative, a Plan B, or as closed.
        - "kind": "sight" (museum, monument, site, market, garden, attraction,
          a mosque or church that is visited), "food" (restaurant, café, bar),
          "area" (neighbourhood, street, square, beach, or a whole town), or
          "stay" (hotel, riad, hostel).
        - "city": the town or city where that day mostly takes place. For a day
          trip, the town visited.
        - At most {MAX_STOPS_PER_DAY} places per day, the most important first
          but kept in visiting order. If the text has no days, use day 1.
        - "destination": the main city or region of the whole trip, with its
          country, e.g. "Tunis, Tunisia".
        - "start_date": the first day as YYYY-MM-DD only if the text states the
          dates with a year; otherwise "".

        Return JSON only:
        {{"destination": "...", "start_date": "", "days": [
          {{"day": 1, "city": "...", "stops": [{{"name": "...", "local": "", "kind": "sight"}}]}}]}}

        Itinerary:
        {text[:MAX_TEXT_CHARS]}
        """
    ).strip()
    # The fast main model first: a traveller is waiting on this call.
    return complete_json(prompt, model=config.discovery_model(), max_tokens=6000)


def _parse_days(data: dict, destination: str, max_stops: int) -> tuple[list[dict], list[Stop], bool]:
    """Normalise the model's answer into day records and stops."""
    days: list[dict] = []
    stops: list[Stop] = []
    raw_days = [d for d in data.get("days") or [] if isinstance(d, dict)][:MAX_DAYS]
    per_day_stops: list[list[Stop]] = []
    trimmed = False
    for index, raw in enumerate(raw_days, 1):
        try:
            number = int(raw.get("day") or index)
        except (TypeError, ValueError):
            number = index
        city = str(raw.get("city") or "").strip()
        days.append({"number": number, "city": city})
        seen: set[str] = set()
        kept: list[Stop] = []
        for entry in raw.get("stops") or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            key = name.lower()
            if not name or key in seen or key in (city.lower(), destination.lower()):
                continue
            seen.add(key)
            if len(kept) >= MAX_STOPS_PER_DAY:
                trimmed = True
                continue
            kind = str(entry.get("kind") or "sight").lower()
            local = str(entry.get("local") or "").strip()
            kept.append(Stop(
                day=number, name=name[:120], kind=kind if kind in _KINDS else "sight", city=city,
                local_name=local[:120] if local.lower() != key else "",
            ))
        per_day_stops.append(kept)
    # Over budget: drop the last place of the fullest day until it fits, so a
    # long trip is still checked from its first day to its last.
    while sum(len(d) for d in per_day_stops) > max_stops:
        max(per_day_stops, key=len).pop()
        trimmed = True
    stops = [stop for day_stops in per_day_stops for stop in day_stops]
    return days, stops, trimmed


# --- Checking against the map ------------------------------------------------------


def _plausible(kind: str, place: Place) -> bool:
    if kind == "food":
        if place.category == "shop":
            return place.osm_type in _FOOD_SHOPS
        return place.category not in _NOT_FOOD
    if kind == "sight":
        return place.category not in _NOT_SIGHT
    return True


def _locate(stop: Stop, destination: str) -> Place | None:
    near = stop.city or destination
    anchor = geocode(near) if near else None
    if anchor is None and destination and near != destination:
        near, anchor = destination, geocode(destination)
    place = verify_place(stop.name, near)
    if place is None and stop.local_name:
        place = verify_place(stop.local_name, near)
    if place is not None and not _plausible(stop.kind, place):
        # Same name, different business: look again without the local preference.
        wider = geocode(stop.name, anchor.country_code if anchor else "")
        place = wider if wider is not None and _plausible(stop.kind, wider) else None
    if place is None:
        stop.status = "not_found"
        return None
    stop.lat, stop.lon, stop.osm_url = place.lat, place.lon, place.osm_url
    stop.where = place.locality
    stop.status = "found"
    if anchor is not None and anchor.is_city:
        km = distance_km(anchor, place)
        stop.distance_km = round(km)
        if km > FAR_KM:
            stop.status = "far"
    return place


def _fold(text: str) -> str:
    """Lower-case, accent-free, single-spaced: "Café des Délices" -> "cafe des delices"."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w]+", " ", text).strip()


def _web_query(stop: Stop, destination: str) -> str:
    return f'"{stop.name}" {stop.city or destination}'.strip()


def _warm(query: str) -> None:
    """Run a search now so its answer is cached when it is needed."""
    try:
        search(query)
    except SearchError:
        pass


def _web_trace(stops: list[Stop], destination: str) -> None:
    """Look on the web for places the map doesn't have.

    OpenStreetMap misses real places (and has them under local names), so
    "not on the map" alone proves little. A place that neither the map nor a
    web search knows is the one worth a strong warning. Sights first: they
    are what a day is built around.
    """
    missing = [s for s in stops if s.status == "not_found"]
    missing.sort(key=lambda s: 0 if s.kind in ("sight", "area") else 1)
    for stop in missing[:MAX_WEB_LOOKUPS]:
        try:
            results = search(_web_query(stop, destination))
        except SearchError:
            return  # search is down or out of budget: leave them "not found"
        wanted = [_fold(n) for n in (stop.name, stop.local_name) if n]
        hits = [
            r for r in results
            if any(w and w in _fold(f"{r.get('title', '')} {r.get('snippet', '')}") for w in wanted)
        ]
        if len(hits) >= 2:
            stop.status, stop.web_source = "web", hits[0].get("link", "")
        else:
            stop.status = "no_trace"


def _check_hours(stops: list[Stop], located: dict[str, Place], destination: str) -> None:
    """Weekly closing days for the sights that were found."""
    by_city: dict[str, list[hours.PlaceCheck]] = {}
    chosen: dict[str, hours.PlaceCheck] = {}
    for stop in stops:
        if stop.kind != "sight" or stop.name not in located or stop.name in chosen:
            continue
        if len(chosen) >= MAX_HOURS_LOOKUPS:
            break
        check = hours.PlaceCheck(name=stop.name, days=[stop.day], on_map=True, osm_url=stop.osm_url,
                                 lat=stop.lat, lon=stop.lon)
        chosen[stop.name] = check
        by_city.setdefault(stop.city or destination, []).append(check)
    for city, checks in by_city.items():
        try:
            # The main model: closing days are the finding people act on,
            # and the small fast model reads fewer of them out of the snippets.
            hours._lookup(checks, city, located, config.litellm_model())
        except Exception as exc:  # hours are a bonus; the map check still stands
            log.warning("Hours lookup failed for %s: %s", city, exc)
    for stop in stops:
        check = chosen.get(stop.name)
        if check is None or stop.kind != "sight":
            continue
        stop.hours, stop.closed_days = check.hours, list(check.closed_days)
        stop.hours_source = check.source
        stop.hours_status = "ok" if check.status == "ok" else "unverified"


# --- Turning what was found into findings --------------------------------------------


def _day_dates(days: list[dict], start: date | None) -> None:
    for day in days:
        when = start + timedelta(days=day["number"] - 1) if start else None
        day["date"] = when.isoformat() if when else ""
        day["weekday"] = f"{when:%A}" if when else ""


def _join(names: list[str]) -> str:
    return ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]


def _issues(days: list[dict], stops: list[Stop], start: date | None, halal: bool,
            country: str) -> list[Issue]:
    found: list[Issue] = []
    by_day = {d["number"]: d for d in days}

    # Closed on the day it is scheduled (or, without dates, a day to watch).
    for stop in stops:
        day = by_day.get(stop.day, {})
        if stop.moved_from is not None:
            found.append(Issue(
                "note", "moved", f"{stop.name} was moved to Day {stop.day}",
                f"It was on Day {stop.moved_from}, when it is closed "
                f"({_join(stop.closed_days)}).", stop.day, stop.name, stop.hours_source,
            ))
        elif stop.closed_days and day.get("weekday") in stop.closed_days:
            found.append(Issue(
                "problem", "closed", f"{stop.name} is closed on {day['weekday']}s",
                f"The plan puts it on Day {stop.day}, a {day['weekday']}."
                + (f" Usual hours: {stop.hours}." if stop.hours else "")
                + " Move it to another day.", stop.day, stop.name, stop.hours_source,
            ))
        elif stop.closed_days and not start:
            found.append(Issue(
                "note", "closing_day", f"{stop.name} is closed on {_join([d + 's' for d in stop.closed_days])}",
                f"It is on Day {stop.day}. Add your first day above and we'll check the weekday for you.",
                stop.day, stop.name, stop.hours_source,
            ))

    # Found, but far from where the day is set.
    for stop in stops:
        if stop.status != "far":
            continue
        where = f"The map puts it in {stop.where}. " if stop.where else ""
        found.append(Issue(
            "problem" if stop.kind in ("food", "stay") else "warning", "far",
            f"{stop.name} is about {stop.distance_km} km from {stop.city}",
            where + (
                "A meal or a bed that far away usually means the plan named the wrong place."
                if stop.kind in ("food", "stay")
                else f"Either the plan means a different place, or this is a long detour for Day {stop.day}."
            ), stop.day, stop.name,
        ))

    # Not on the map: no trace anywhere, seen on the web only, or not searched.
    for stop in stops:
        if stop.status == "no_trace":
            found.append(Issue(
                "problem", "no_trace", f"No trace of {stop.name}",
                f"It is not on the map near {stop.city or 'the destination'} and a web search for the "
                "exact name found nothing. AI planners do invent places: confirm it exists before "
                f"Day {stop.day} depends on it.", stop.day, stop.name,
            ))
    unmapped = [s.name for s in stops if s.status == "web"]
    if unmapped:
        found.append(Issue(
            "note", "web_only",
            f"{len(unmapped)} place{'s' if len(unmapped) > 1 else ''} found online but not on the map",
            f"{_join(unmapped)}. Probably real, but we couldn't check where "
            f"{'they are' if len(unmapped) > 1 else 'it is'}, so distances for "
            f"{'them' if len(unmapped) > 1 else 'it'} aren't counted.",
        ))
    unsearched = [s.name for s in stops if s.status == "not_found"]
    if unsearched:
        found.append(Issue(
            "warning", "not_found",
            f"{len(unsearched)} place{'s' if len(unsearched) > 1 else ''} couldn't be found on the map",
            f"{_join(unsearched)}. The name may be misspelled or translated, or the place may not "
            "exist. Search for each before you count on it.",
        ))

    # Days that cover too much ground or hold too many sights.
    for day in days:
        path = [
            s for s in stops
            if s.day == day["number"] and s.lat is not None
            and not (s.status == "far" and s.kind in ("food", "stay"))
        ]
        total = sum(
            distance_km(a, b) for a, b in zip(path, path[1:])  # type: ignore[arg-type]
        )
        road = routes.drive([(s.lat, s.lon) for s in path]) if total >= ROUTE_FROM_KM else None
        day["drive_km"] = road["km"] if road else None
        day["drive_minutes"] = road["minutes"] if road else None
        route = " → ".join(s.name for s in path)
        if road and road["minutes"] >= LONG_DRIVE_MINUTES:
            found.append(Issue(
                "warning", "long_day",
                f"Day {day['number']} is about {routes.hours_minutes(road['minutes'])} of driving",
                f"{route}: about {road['km']} km by road, before any return trip, stops or traffic. "
                "Drop a stop or split the day.", day["number"],
            ))
        elif not road and total >= LONG_DAY_KM:
            found.append(Issue(
                "warning", "long_day", f"Day {day['number']} covers about {round(total)} km between stops",
                f"{route}. That is the straight-line distance; roads are "
                "longer, so most of this day is spent travelling.", day["number"],
            ))
        sights = [s for s in stops if s.day == day["number"] and s.kind == "sight"]
        if len(sights) >= PACKED_SIGHTS:
            found.append(Issue(
                "warning", "packed", f"Day {day['number']} lists {len(sights)} sights",
                "Three or four is what fits in a day once travel, queues and meals are counted.",
                day["number"],
            ))

    # Tickets that sell out, and public holidays.
    book = list(dict.fromkeys(
        s.name for s in stops
        if s.kind == "sight" and any(key in _fold(f"{s.name} {s.local_name}") for key in _BOOK_AHEAD)
    ))
    if book:
        found.append(Issue(
            "note", "book_ahead", f"Book ahead: {_join(book)}",
            f"{'These usually need' if len(book) > 1 else 'This usually needs'} a timed ticket bought in "
            "advance, and popular slots sell out days or weeks before. Buy on the official site before "
            "you fix the rest of the day around it.",
        ))
    if start and country:
        for day in days:
            when = day.get("date") or ""
            name = holidays.public_holidays(country, int(when[:4])).get(when) if when else None
            day["holiday"] = name or ""
            if name:
                found.append(Issue(
                    "note", "holiday", f"Day {day['number']} is a public holiday: {name}",
                    "Museums, shops and public transport often close or keep reduced hours. Check each "
                    "sight's opening times for that date.", day["number"],
                ))

    # Fridays and Ramadan.
    for day in days:
        if day.get("weekday") != "Friday":
            continue
        mosques = [s.name for s in stops if s.day == day["number"] and _MOSQUE.search(s.name)]
        if mosques:
            found.append(Issue(
                "note", "friday", f"Day {day['number']} is a Friday",
                f"{_join(mosques)}: mosques usually close to visitors around the midday prayer on "
                "Fridays. Go early or late.", day["number"],
            ))
        elif halal:
            found.append(Issue(
                "note", "friday", f"Day {day['number']} is a Friday",
                "Keep about 12:00 to 14:00 free for the Friday prayer, and expect some shops and "
                "sites to pause around it.", day["number"],
            ))
    if start and days and country in _RAMADAN_COUNTRIES:
        try:
            ramadan = ramadan_days(start, start + timedelta(days=max(d["number"] for d in days) - 1))
        except Exception:  # calendar lookup failed: say nothing rather than guess
            ramadan = []
        if ramadan:
            found.append(Issue(
                "note", "ramadan", "This trip falls in Ramadan",
                f"{ramadan[0]:%d %B} to {ramadan[-1]:%d %B %Y} (calculated; the local start can differ "
                "by a day). Many restaurants close in daylight and sites keep shorter hours, so "
                "confirm each day's opening times.",
            ))

    if not start and any(s.kind == "sight" for s in stops):
        found.append(Issue(
            "note", "no_dates", "Closing days weren't matched to weekdays",
            "Add the first day of your trip and run the check again to see which visits fall on a "
            "day the place is closed.",
        ))
    order = {"problem": 0, "warning": 1, "note": 2}
    return sorted(found, key=lambda i: (order[i.level], i.day or 0))


def _summary(stops: list[Stop], issues: list[Issue]) -> dict:
    sights = [s for s in stops if s.kind == "sight"]
    return {
        "places": len(stops),
        "confirmed": sum(s.status == "found" for s in stops),
        "far": sum(s.status == "far" for s in stops),
        "online_only": sum(s.status == "web" for s in stops),
        "not_found": sum(s.status in ("not_found", "no_trace") for s in stops),
        "no_trace": sum(s.status == "no_trace" for s in stops),
        "sights": len(sights),
        "hours_checked": sum(s.hours_status == "ok" for s in sights),
        "problems": sum(i.level == "problem" for i in issues),
        "warnings": sum(i.level == "warning" for i in issues),
        "notes": sum(i.level == "note" for i in issues),
    }


def _fix_prompt(issues: list[Issue]) -> str:
    """A message to paste back into the assistant that wrote the plan."""
    lines = [
        f"{n}. {i.title}. {i.detail}".strip()
        for n, i in enumerate((i for i in issues if i.level != "note"), 1)
    ]
    if not lines:
        return ""
    return (
        "An independent check of this itinerary against OpenStreetMap and published opening "
        "hours found these problems. Please fix them and keep everything else the same:\n\n"
        + "\n".join(lines)
        + "\n\nFor each restaurant or hotel you keep, give its exact address so I can verify it."
    )


def _result(destination: str, start: date | None, halal: bool, days: list[dict],
            stops: list[Stop], country: str, notes: list[str]) -> dict:
    _day_dates(days, start)
    issues = _issues(days, stops, start, halal, country)
    return {
        "destination": destination,
        "start_date": start.isoformat() if start else "",
        "halal": halal,
        "days": days,
        "stops": [asdict(s) for s in stops],
        "issues": [asdict(i) for i in issues],
        "summary": _summary(stops, issues),
        "fix_prompt": _fix_prompt(issues),
        "notes": notes,
    }


# --- Entry points ----------------------------------------------------------------------


def _run(text: str, start: date | None, halal: bool, destination: str,
         on_progress: Progress | None, max_stops: int):
    text = (text or "").strip()
    if len(text) < 40:
        raise ReviewError("Paste the itinerary itself: the day-by-day plan with its places.")
    notes = []
    if len(text) > MAX_TEXT_CHARS:
        notes.append(f"Only the first {MAX_TEXT_CHARS:,} characters were read.")
    progress = on_progress or (lambda *_a: None)
    progress(0, 0, "Reading the itinerary")
    try:
        data = _extract(text, destination)
    except Exception as exc:
        raise ReviewError("The AI step is busy right now. Please try again in a minute.") from exc
    destination = destination.strip() or str(data.get("destination") or "").strip()
    days, stops, trimmed = _parse_days(data, destination, max_stops)
    if not stops:
        raise ReviewError(
            "We couldn't find named places in this text. Paste a day-by-day plan that names "
            "the sights, restaurants or towns."
        )
    if trimmed:
        notes.append(f"Long itinerary: the first {len(stops)} places were checked, spread over every day.")
    if start is None:
        try:
            start = date.fromisoformat(str(data.get("start_date") or ""))
        except ValueError:
            start = None

    # Map lookups are spaced a second apart, so the web searches that follow
    # (opening hours, places missing from the map) start meanwhile: by the
    # time the last place is located their answers are already cached.
    located: dict[str, Place] = {}
    sights, missing = 0, 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, stop in enumerate(stops):
            progress(index, len(stops), stop.name)
            place = _locate(stop, destination)
            city = stop.city or destination
            if place is None:
                if missing < MAX_WEB_LOOKUPS:
                    missing += 1
                    pool.submit(_warm, _web_query(stop, destination))
                continue
            if stop.kind == "sight" and stop.name not in located and sights < MAX_HOURS_LOOKUPS:
                sights += 1
                if (
                    hours.closed_days.lookup(stop.name, place.country_code) is None
                    and hours.osm_closed_days(place.opening_hours) is None
                    and not storage.load("hours", hours._cache_key(stop.name, city))
                ):
                    pool.submit(_warm, hours.hours_query(stop.name, city))
            located[stop.name] = place
        progress(len(stops), len(stops), "Checking opening days")
    _web_trace(stops, destination)
    _check_hours(stops, located, destination)
    anchor = geocode(destination) if destination else None
    country = anchor.country_code if anchor else next(
        (p.country_code for p in located.values()), ""
    )
    return destination, start, days, stops, country, notes


def run(text: str, start: date | None = None, halal: bool = False, destination: str = "",
        on_progress: Progress | None = None, max_stops: int = MAX_STOPS) -> dict:
    """Check an itinerary; returns the report as a plain dict.

    Raises :class:`ReviewError` (with a message for the user) when the text
    can't be read as an itinerary.
    """
    destination, start, days, stops, country, notes = _run(
        text, start, halal, destination, on_progress, max_stops
    )
    return _result(destination, start, halal, days, stops, country, notes)


def check_plan(plan: str, city: str, travel_dates: str, halal: bool = False,
               on_progress: Progress | None = None) -> tuple[str, dict | None]:
    """Check a plan ReelTrip just wrote, and move visits off closed days.

    Returns the (possibly corrected) plan and its report. Never raises: if the
    check fails the plan comes back unchanged with no report.
    """
    try:
        parsed = parse_date_range(travel_dates)
        destination, start, days, stops, country, notes = _run(
            plan, parsed[0] if parsed else None, halal, city, on_progress, max_stops=22
        )
        _day_dates(days, start)
        weekday = {d["number"]: d["weekday"] for d in days}
        closed = {s.name: s for s in stops if s.closed_days and weekday.get(s.day) in s.closed_days}
        if closed:
            sections = split_days(plan, travel_dates)
            checks = [
                hours.PlaceCheck(name=s.name, closed_days=s.closed_days, hours=s.hours, status="ok")
                for s in closed.values()
            ]
            conflicts = hours._conflicts(sections, checks)
            fixed = hours._fix(plan, conflicts, travel_dates) if conflicts else ""
            if fixed:
                plan, sections = fixed, split_days(fixed, travel_dates)
                still = {c.name for c, _ in hours._conflicts(sections, checks)}
                for name, stop in closed.items():
                    if name in still:
                        continue
                    now = [d.number for d in sections if hours._mentions(d, name)]
                    if now and now[0] != stop.day:
                        stop.moved_from, stop.day = stop.day, now[0]
                    elif not now:
                        # No open day fitted, so the edit swapped it for
                        # something else: the report must not list a visit
                        # the plan no longer has.
                        stops.remove(stop)
                        notes.append(
                            f"{name} is closed on {weekday[stop.day]}s, the day it was planned, "
                            "so it was replaced in the plan. The replacement was not checked."
                        )
            plan = hours._warn(plan, hours._conflicts(sections, checks))
        return plan, _result(destination, start, halal, days, stops, country, notes)
    except Exception as exc:  # the check is a bonus, never a failure point
        log.warning("Plan check failed: %s", exc)
        return plan, None


def rewrite(text: str, report: dict) -> str:
    """Rewrite an itinerary so the problems a check found are fixed.

    One model call. The result is not trusted: the caller checks it again,
    and the second report says what is still wrong.
    """
    findings = "\n".join(
        f"- {i['title']}. {i['detail']}" for i in report.get("issues", []) if i["level"] != "note"
    )
    days = report.get("days") or []
    calendar = "\n".join(
        f"Day {d['number']}: {d['weekday']} {d['date']}" for d in days if d.get("weekday")
    )
    closing = "\n".join(
        f"- {s['name']}: closed {', '.join(s['closed_days'])}"
        for s in report.get("stops", []) if s.get("closed_days")
    )
    prompt = dedent(
        f"""
        Below is a trip itinerary and the problems an independent check found in
        it. Rewrite the itinerary so every problem is fixed.

        How to fix each kind of problem:
        - A visit on a day the place is closed: move it to a day of this trip
          when it is open, swapping it with something from that day.
        - A sight with no trace: remove it, or replace it with a major sight
          of that town that you are certain exists.
        - A restaurant, café or hotel with no trace, or far from the town its
          day is set in: do NOT name another business. Write the meal or night
          generically instead ("lunch in the medina of Kairouan, near the
          Great Mosque"), so the traveller picks a place on the day.
        - Never invent a name.
        - A day with too much driving or too many sights: drop or move stops so
          the day fits, and say which.
        Keep the same number of days, the same "Day N" headings, the same
        language as the itinerary, the traveller's interests, and every part
        that had no problem. Do not add new problems: keep closed days in mind
        for everything you move.

        {"Trip calendar:" if calendar else ""}
        {calendar}
        {"Known closing days:" if closing else ""}
        {closing}

        Problems found:
        {findings}

        Write the corrected itinerary only, then a last section headed
        "What changed" with one short bullet per change.

        Itinerary:
        {text[:MAX_TEXT_CHARS]}
        """
    ).strip()
    response = complete(
        model=config.litellm_model(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=4000,
        num_retries=2,
    )
    fixed = (response.choices[0].message.content or "").strip()
    fixed = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", fixed)
    fixed = fixed.translate({0x202F: " ", 0x00A0: " ", 0x2007: " ", 0x2011: "-"})
    if len(fixed) < 0.4 * len(text):
        raise ReviewError("The rewrite came back incomplete. Please try again in a minute.")
    return fixed


def legacy_checks(report: dict | None) -> list[dict]:
    """The report's sights in the older per-place shape (share images, captions)."""
    if not report:
        return []
    by_name = {}
    for stop in report["stops"]:
        if stop["kind"] != "sight" or stop["lat"] is None:
            continue
        conflict = any(
            i["kind"] == "closed" and i["stop"] == stop["name"] for i in report["issues"]
        )
        status = (
            "moved" if stop["moved_from"] is not None
            else "warning" if conflict
            else "ok" if stop["hours_status"] == "ok"
            else "unverified"
        )
        entry = by_name.setdefault(stop["name"], {
            "name": stop["name"], "days": [], "on_map": True, "osm_url": stop["osm_url"],
            "lat": stop["lat"], "lon": stop["lon"], "hours": stop["hours"],
            "closed_days": stop["closed_days"], "source": stop["hours_source"], "status": status,
        })
        entry["days"].append(stop["day"])
    return list(by_name.values())
