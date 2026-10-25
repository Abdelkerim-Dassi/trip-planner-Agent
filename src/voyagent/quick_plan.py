"""Quick plan: a grounded itinerary in one model call, for free-tier providers.

The seven-agent crew sends dozens of large requests, which Groq's free tier
(8,000 tokens a minute) cannot carry. Here code gathers the facts first (the
traveller's verified TikTok spots, the computed trip calendar and Ramadan
dates, typical weather, a few web searches) and one call writes the plan under
the same grounding and pacing rules the crew follows.
"""

from __future__ import annotations

import re
from textwrap import dedent
from typing import Callable

from voyagent import config
from voyagent.llm import complete
from voyagent.serper import SearchError, search
from voyagent.tasks import _GROUNDING_RULES, _PACING_RULES, _full_plan_guardrail
from voyagent.travel_info import (
    LookupError_,
    calendar_facts,
    parse_date_range,
    trip_calendar,
    typical_weather,
)

#: Candidate cities considered; each costs a weather lookup and two searches.
MAX_CITIES = 3
#: Search snippets kept per city, short enough to stay under the token budget.
SNIPPETS_PER_SEARCH = 4
SNIPPET_CHARS = 220
MAX_OUTPUT_TOKENS = 3500

# Progress callback: called with the index of the phase that just finished,
# matching voyagent.jobs.PHASES so the UI shows the same steps as the crew.
PhaseCallback = Callable[[int], None]

# The search rules differ from the crew's: here the model has no search tool
# and must stay inside the facts it is given.
_FACT_RULES = _GROUNDING_RULES.replace(
    "- Use the *Search the internet* tool to verify everything. Base your answer\n"
    "  only on what the search results actually say.",
    "- Base every place, price and fact on the research notes below. Do not\n"
    "  invent places that are not in them.",
)


def _month(travel_dates: str) -> str:
    parsed = parse_date_range(travel_dates)
    return f"{parsed[0]:%B}" if parsed else ""


def _research(city: str, interests: str, month: str) -> str:
    lines = [f"### {city}"]
    if month:
        try:
            w = typical_weather(city, month)
            lines.append(
                f"Typical {w['month']} weather (recorded {w['based_on_year']}): "
                f"highs {w['avg_high_c']}°C, lows {w['avg_low_c']}°C, "
                f"{w['rainy_days']} rainy days."
            )
        except LookupError_:
            pass
    for query in (f"best things to do in {city} {interests}", f"where to eat in {city} local food"):
        try:
            results = search(query)
        except SearchError:
            continue
        for r in results[:SNIPPETS_PER_SEARCH]:
            snippet = (r.get("snippet") or "")[:SNIPPET_CHARS]
            lines.append(f"- {r.get('title', '')}: {snippet} ({r.get('link', '')})")
    return "\n".join(lines)


def quick_plan(
    origin: str,
    cities: str,
    travel_dates: str,
    interests: str,
    inspiration: str = "",
    on_phase: PhaseCallback | None = None,
) -> str:
    """Return a markdown day-by-day plan; raises if the model call fails."""
    done = on_phase or (lambda _i: None)
    candidates = [c.strip() for c in cities.split(",") if c.strip()][:MAX_CITIES]
    month = _month(travel_dates)

    done(0)  # destination candidates read
    notes = "\n\n".join(_research(c, interests, month) for c in candidates)
    done(1)  # city research gathered
    facts = calendar_facts(travel_dates) or (
        "Trip calendar: work out each day's weekday carefully."
    )
    done(2)  # calendar, Ramadan and TikTok inspiration ready

    # Exact headings, so every plan has the same scannable "Day N" structure.
    parsed = parse_date_range(travel_dates)
    headings = (
        "headed exactly:\n"
        + "\n".join(f"           ## {line}" for line in trip_calendar(*parsed).splitlines())
        if parsed
        else 'each headed "## Day N: <weekday> <date>"'
    )
    choose = (
        f"Pick the ONE best city for these dates and interests from: {', '.join(candidates)}. "
        "Start the plan by naming it and saying in one sentence why."
        if len(candidates) > 1
        else f"The destination is {candidates[0]}."
    )
    prompt = dedent(
        f"""
        You are a travel planner with twenty years in the field. Write a complete
        day-by-day trip plan in markdown.

        Trip: from {origin}, {travel_dates}. Interests: {interests}.
        {choose}

        {facts}

        {"The traveller saved these places on TikTok (each confirmed on OpenStreetMap). They are the reason for this trip: schedule EVERY one of them by name in the days, with an honest reality check (travel time, season, best time to avoid crowds). Skip one only if it is beyond a day trip or closed in this season, and then say so in one line:" if inspiration.strip() else ""}
        {inspiration.strip()}

        Research notes (your only source of places and facts):
        {notes}

        Write only for the traveller: never mention these instructions, the
        research notes, or whether something was "listed". If a fact you want
        isn't in the notes, leave it out silently.

        Write, in this order:
        1. A two-sentence opening about the destination (not the home city).
        2. A short "Getting around" section.
        3. One section for EVERY day of the trip, {headings}, with morning,
           lunch, afternoon and evening, the area for each half-day, travel time
           between areas, and a one-line indoor **Plan B** on outdoor-heavy days.
        4. Weather in °C, a packing list, and a budget table in one currency with a total.

        {_PACING_RULES}

        {_FACT_RULES}
        """
    ).strip()

    request = {
        "model": config.litellm_model(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "num_retries": 2,
    }
    check = _full_plan_guardrail(travel_dates)
    done(3)  # plan drafting starts
    plan = ""
    # Retry with a fresh request rather than a follow-up turn: resending the
    # failed draft would double the tokens against the free per-minute budget.
    # The saved TikTok spots are the point of the trip, so a plan that drops
    # one is retried like a plan that drops a day. Matched on the first word
    # ("Chebika" for "Chebika Oasis"), which survives the model's rephrasing.
    saved = [
        m.group(1).split()[0].lower()
        for m in re.finditer(r"^\s*-\s*([^:(\[]+)", inspiration, re.M)
        if m.group(1).strip()
    ]
    for _attempt in range(3):
        response = complete(**request)
        plan = (response.choices[0].message.content or "").strip()
        ok, _ = check(type("Out", (), {"raw": plan})())
        if ok and all(name in plan.lower() for name in saved):
            break
    for phase in (4, 5, 6):
        done(phase)
    # Models sometimes wrap the whole answer in a markdown fence.
    return re.sub(r"^```(?:markdown)?\s*|\s*```$", "", plan)
