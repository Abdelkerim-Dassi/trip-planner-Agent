"""Opening-hours check: catch plans that send people to closed places.

AI itineraries most often go wrong on opening days (a 2024 test of ChatGPT
plans found half scheduled visits outside opening hours; our own live test put
Tunis's Bardo Museum on a Monday, when it is closed). After a plan is written:

1. a small model lists the attractions the plan schedules, day by day;
2. each one's weekly closing days come from OpenStreetMap's ``opening_hours``
   tag when it is mapped, otherwise from web-search snippets read by the model
   (only when a snippet states it), cached for a month so popular sights cost
   nothing the second time;
3. a place scheduled on a day it is closed is moved by one editing call, and
   anything still in conflict gets a visible warning in that day.

The result also records what was checked, which the plan page shows as badges.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import asdict, dataclass, field
from textwrap import dedent

from voyagent import config, storage
from voyagent.llm import complete, complete_json
from voyagent.places import verify_place
from voyagent.plan_text import _DAY_HEADING, Day, split_days
from voyagent.serper import SearchError, search

log = logging.getLogger(__name__)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_OSM_DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
#: Most places checked per plan (each may cost a search credit when not cached).
MAX_PLACES = 8
SNIPPETS_PER_PLACE = 3
CACHE_TTL_SECONDS = 30 * 24 * 3600
#: Places with no hours found are retried sooner: pages get updated.
UNVERIFIED_TTL_SECONDS = 7 * 24 * 3600


@dataclass
class PlaceCheck:
    name: str
    days: list[int] = field(default_factory=list)  # day numbers it is scheduled on
    on_map: bool = False
    osm_url: str = ""
    lat: float | None = None
    lon: float | None = None
    hours: str = ""  # e.g. "Tu-Su 09:30-16:30"
    closed_days: list[str] = field(default_factory=list)  # weekday names
    source: str = ""  # "OpenStreetMap" or a web page URL
    status: str = "unverified"  # ok | moved | warning | unverified

    def to_dict(self) -> dict:
        return asdict(self)


# --- OpenStreetMap opening_hours -------------------------------------------


def _expand_days(selector: str) -> set[int] | None:
    """"Mo-Fr,Su" -> {0,1,2,3,4,6}; None if it isn't a plain weekday list."""
    result: set[int] = set()
    for part in selector.split(","):
        part = part.strip()
        if not part:
            continue
        bounds = part.split("-")
        if any(b not in _OSM_DAYS for b in bounds) or len(bounds) > 2:
            return None
        first = _OSM_DAYS.index(bounds[0])
        last = _OSM_DAYS.index(bounds[-1])
        day = first
        while True:
            result.add(day)
            if day == last:
                break
            day = (day + 1) % 7
    return result


def osm_closed_days(spec: str) -> list[str] | None:
    """Weekdays a place is closed all day, from an OSM ``opening_hours`` value.

    Handles the common forms ("Tu-Su 09:00-17:00", "Mo-Fr 08:00-18:00; Sa
    09:00-13:00", "Mo off", "24/7"); returns ``None`` for anything more
    involved (seasons, dates, week numbers) rather than guess.
    """
    spec = (spec or "").strip()
    if not spec:
        return None
    if spec == "24/7":
        return []
    open_days: set[int] = set()
    for rule in re.split(r"\s*;\s*|\s*\|\|\s*", spec):
        rule = rule.strip().rstrip(",")
        if not rule:
            continue
        if re.match(r"^(PH|SH)\b", rule):
            continue  # public/school holidays don't decide the weekly pattern
        match = re.match(r"^((?:Mo|Tu|We|Th|Fr|Sa|Su)[A-Za-z,\- ]*?)(?:\s+(.*))?$", rule)
        if match:
            days = _expand_days(match.group(1).replace(" ", ""))
            rest = (match.group(2) or "").strip().strip('"')
        else:
            days, rest = set(range(7)), rule
        if days is None:
            return None
        if re.fullmatch(r"(off|closed)(\s+\".*\")?", rest, re.IGNORECASE):
            open_days -= days
        elif re.fullmatch(r"[\d:,\- +]+", rest) or rest.lower() in {"open", ""}:
            open_days |= days
        else:
            return None
    return [WEEKDAYS[d] for d in range(7) if d not in open_days]


# --- Finding what the plan schedules -----------------------------------------


def _scheduled_places(days: list[Day], city: str) -> list[str]:
    """Ask a small model for the attractions with opening hours in the plan."""
    if not days:
        return []
    numbered = "\n\n".join(f"Day {d.number}:\n" + "\n".join(d.items or [d.text[:800]]) for d in days)
    prompt = dedent(
        f"""
        Below is a day-by-day trip plan for {city}. List the specific, named
        places in it that have opening hours a visitor must respect: museums,
        monuments, archaeological sites, palaces, mosques or churches open to
        visitors, markets, gardens, attractions with tickets.

        Rules:
        - Copy each name EXACTLY as it is written in the plan.
        - Skip restaurants, cafés, hotels, streets, neighbourhoods, beaches,
          whole towns, and transport.
        - At most {MAX_PLACES}, most important first.

        Return JSON only: {{"places": ["...", "..."]}}

        {numbered[:6000]}
        """
    ).strip()
    names: list[str] = []
    for _attempt in range(2):  # thinking models occasionally return nothing
        try:
            data = complete_json(prompt, max_tokens=3000)
        except Exception as exc:  # a failed check must never fail the plan
            log.warning("Place extraction failed: %s", exc)
            return []
        names = [str(n).strip() for n in data.get("places", []) if str(n).strip()]
        if names:
            break
    return list(dict.fromkeys(names))[:MAX_PLACES]


#: A line with one of these only talks about a place ("instead of the closed
#: Bardo"), it doesn't send the traveller there.
_NOT_A_VISIT = re.compile(
    r"\b(closed|instead of|skip|avoid|not open|shut|move[sd]? to|swap)\b", re.IGNORECASE
)


def _distinctive(name: str) -> list[str]:
    """The words that identify a place: "Bardo National Museum" -> ["bardo"]."""
    return [w for w in re.findall(r"[\w'-]{4,}", name.lower())
            if w not in {"museum", "national", "mosque", "palace", "market", "garden",
                         "gardens", "site", "ruins", "church", "great", "grand", "old"}]


def _mentions(day: Day, name: str) -> bool:
    """Whether the day sends the traveller to ``name``."""
    # "Bardo National Museum" vs "Bardo Museum": also match on the distinctive word.
    keys = [name.lower()] + _distinctive(name)[:1]
    for line in day.text.lower().splitlines():
        if any(k in line for k in keys) and not _NOT_A_VISIT.search(line):
            return True
    return False


# --- Looking up closing days ---------------------------------------------------


def _cache_key(name: str, city: str) -> str:
    return hashlib.sha1(f"{name.lower()}|{city.lower()}".encode()).hexdigest()[:24]


def _from_snippets(pending: list[PlaceCheck], city: str) -> set[str]:
    """Fill closing days from web-search snippets, one model call for all.

    Returns the names the model actually answered for ("known" or "unknown"),
    so a failed or empty call isn't cached as "no hours published".
    """
    blocks, sources = [], {}
    for index, check in enumerate(pending):
        try:
            results = search(f"{check.name} {city} opening hours closed days")
        except SearchError:
            continue
        lines = []
        for r in results[:SNIPPETS_PER_PLACE]:
            lines.append(f"  - ({r.get('link', '')}) {(r.get('snippet') or '')[:260]}")
        if lines:
            blocks.append(f"[{index}] {check.name}\n" + "\n".join(lines))
            sources[index] = [r.get("link", "") for r in results[:SNIPPETS_PER_PLACE]]
    if not blocks:
        return set()
    prompt = dedent(
        f"""
        For each place below (in or near {city}), read ONLY the search snippets
        given and report its usual opening hours and the weekdays it is closed
        ALL day. If the snippets don't clearly say, use "unknown": never guess.

        Return JSON only:
        {{"places": [{{"id": 0, "status": "known|unknown", "hours": "09:30-16:30",
          "closed_days": ["Monday"], "source": "the snippet URL that says it"}}]}}
        ("closed_days" is [] when it is open every day.)

        {chr(10).join(blocks)}
        """
    ).strip()
    try:
        data = complete_json(prompt, max_tokens=4000)
    except Exception as exc:
        log.warning("Hours extraction failed: %s", exc)
        return set()
    answered: set[str] = set()
    for entry in data.get("places", []):
        if not isinstance(entry, dict):
            continue
        try:
            check = pending[int(entry.get("id"))]
        except (TypeError, ValueError, IndexError):
            continue
        answered.add(check.name)
        if entry.get("status") != "known":
            continue
        closed = [d.capitalize() for d in entry.get("closed_days") or [] if d.capitalize() in WEEKDAYS]
        source = str(entry.get("source") or "")
        if source not in sources.get(int(entry["id"]), []):
            continue  # must point at a snippet we actually showed it
        check.closed_days = closed
        check.hours = str(entry.get("hours") or "")[:60]
        check.source = source
        check.status = "ok"
    return answered


def _lookup(checks: list[PlaceCheck], city: str) -> None:
    pending, from_cache, answered = [], set(), set()
    for check in checks:
        cached = storage.load("hours", _cache_key(check.name, city))
        if cached:
            for key in ("on_map", "osm_url", "lat", "lon", "hours", "closed_days", "source", "status"):
                setattr(check, key, cached.get(key, getattr(check, key)))
            from_cache.add(check.name)
            continue
        place = verify_place(check.name, city)
        if place is not None:
            check.on_map, check.osm_url = True, place.osm_url
            check.lat, check.lon = place.lat, place.lon
            closed = osm_closed_days(place.opening_hours)
            if closed is not None:
                check.hours, check.closed_days = place.opening_hours, closed
                check.source, check.status = "OpenStreetMap", "ok"
        if check.status != "ok":
            pending.append(check)
    if pending:
        answered = _from_snippets(pending, city)
    for check in checks:
        if check.name in from_cache:
            continue
        # Cache what we found, and "no hours published" only when the model
        # really answered; a failed call is retried next time.
        if check.status == "ok" or check.name in answered:
            data = check.to_dict()
            data.pop("days")
            data.pop("name")
            ttl = CACHE_TTL_SECONDS if check.status == "ok" else UNVERIFIED_TTL_SECONDS
            storage.save("hours", _cache_key(check.name, city), data, ttl)


# --- Fixing conflicts ------------------------------------------------------------


def _conflicts(days: list[Day], checks: list[PlaceCheck]) -> list[tuple[PlaceCheck, Day]]:
    found = []
    for check in checks:
        for day in days:
            if day.weekday and day.weekday in check.closed_days and _mentions(day, check.name):
                found.append((check, day))
    return found


def _describe(conflicts: list[tuple[PlaceCheck, Day]]) -> str:
    return "\n".join(
        f"- {c.name} is scheduled on {d.heading}, but it is closed on "
        f"{', '.join(c.closed_days)}" + (f" (hours: {c.hours})" if c.hours else "") + "."
        for c, d in conflicts
    )


def _fix(plan: str, conflicts: list[tuple[PlaceCheck, Day]], travel_dates: str) -> str:
    """One editing call that moves closed places to open days; "" on failure."""
    prompt = dedent(
        f"""
        Here is a finished trip plan in markdown. These visits fall on days the
        place is closed:
        {_describe(conflicts)}

        Move each of them to a day of this trip when it is open (swap it with
        another activity if needed), or replace it with a nearby alternative if
        no day works. Keep the day headings, structure, tone and everything
        else exactly as it is. Return the complete corrected plan only.

        {plan}
        """
    ).strip()
    try:
        response = complete(
            model=config.litellm_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=4000,
            num_retries=2,
        )
    except Exception as exc:
        log.warning("Plan fix failed: %s", exc)
        return ""
    fixed = (response.choices[0].message.content or "").strip()
    fixed = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", fixed)
    # Same clean-up as quick_plan: gpt-oss writes narrow no-break spaces.
    fixed = fixed.translate({0x202F: " ", 0x00A0: " ", 0x2007: " ", 0x2011: "-"})
    # The fix must keep every day, or we keep the original.
    if len(split_days(fixed, travel_dates)) < len(split_days(plan, travel_dates)) or len(fixed) < 0.7 * len(plan):
        return ""
    return fixed


def _warn(plan: str, conflicts: list[tuple[PlaceCheck, Day]]) -> str:
    """Put a visible warning under each affected day's heading."""
    for check, day in conflicts:
        note = (
            f"\n\n> ⚠️ **{check.name}** is usually closed on {day.weekday}s"
            + (f" (hours: {check.hours})" if check.hours else "")
            + ". Check before you go or swap it with another day.\n"
        )
        heading = next(
            (m for m in _DAY_HEADING.finditer(plan) if int(m.group(1)) == day.number), None
        )
        if heading is not None:
            plan = plan[: heading.end()] + note + plan[heading.end():]
    return plan


def check_plan(plan: str, city: str, travel_dates: str) -> tuple[str, list[dict]]:
    """Check the plan's attractions against their closing days.

    Returns the (possibly corrected) plan and the per-place checks to show.
    Never raises: on any failure the plan comes back unchanged.
    """
    try:
        days = split_days(plan, travel_dates)
        names = _scheduled_places(days, city)
        # "Bardo Museum" and "Bardo National Museum" are one place: keep the first.
        seen: set[str] = set()
        unique = []
        for name in names:
            key = (_distinctive(name) or [name.lower()])[0]
            if key not in seen:
                seen.add(key)
                unique.append(name)
        names = unique
        if not names:
            return plan, []
        checks = [PlaceCheck(name=n, days=[d.number for d in days if _mentions(d, n)]) for n in names]
        _lookup(checks, city)

        conflicts = _conflicts(days, checks)
        if conflicts:
            fixed = _fix(plan, conflicts, travel_dates)
            if fixed:
                plan, days = fixed, split_days(fixed, travel_dates)
                for check in {c.name: c for c, _ in conflicts}.values():
                    check.status = "moved"
                    check.days = [d.number for d in days if _mentions(d, check.name)]
            remaining = _conflicts(days, checks)
            for check, _day in remaining:
                check.status = "warning"
            plan = _warn(plan, remaining)
        return plan, [c.to_dict() for c in checks]
    except Exception as exc:  # the check is a bonus, never a failure point
        log.warning("Opening-hours check failed: %s", exc)
        return plan, []


def chosen_city(plan: str, cities: str) -> str:
    """The destination the plan settled on, among the traveller's candidates."""
    candidates = [c.strip() for c in cities.split(",") if c.strip()]
    if len(candidates) <= 1:
        return candidates[0] if candidates else ""
    lower = plan.lower()
    return max(candidates, key=lambda c: lower.count(c.lower()))
