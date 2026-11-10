"""ReelTrip as an MCP server, so Claude, ChatGPT and other assistants can use it.

Inside an assistant the host model is already a capable planner; what it lacks
is grounded, local data. So the main tools are fast lookups (TikTok trends,
place verification, weather, prayer times, transfers). ``plan_trip`` runs the
full seven-agent crew for users who want ReelTrip's own deep plan; it is slow.

Run locally (stdio, e.g. for Claude Desktop):   python -m voyagent.mcp_server
Run as a remote server (streamable HTTP):        python -m voyagent.mcp_server --http
The web app also serves this same server at ``/mcp``.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from datetime import date as _date

import anyio
from mcp.server.mcpserver import Context, MCPServer

from voyagent import limits, places, social, storage, travel_info
from voyagent.jobs import PHASES, CheckJob, PlanJob

PUBLIC_URL = os.environ.get("VOYAGENT_PUBLIC_URL") or os.environ.get(
    "RENDER_EXTERNAL_URL", "https://reeltrip.onrender.com"
)

INSTRUCTIONS = """
ReelTrip checks trip plans against the real world, with a focus on North Africa
and the Middle East (halal-friendly, prayer-time aware) but working worldwide.

When you have written or been given a day-by-day itinerary, call
check_itinerary with its full text before presenting it as final. It looks up
every named place on OpenStreetMap, flags places with no trace on the map or
the web, places far from the town their day is set in, visits on a weekly
closing day, and days that cover too much ground. Fix what it reports, tell the
user what was checked, and give them the share link.

Good workflow for a trip request:
1. trending_spots(destination, month) to see what travellers love on TikTok,
   or spots_from_tiktok_links(links) when the user shares videos they saved.
2. typical_weather and transfer_options to reality-check the ideas: distance,
   season, how to get there.
3. Build the itinerary yourself, grouping places by area.
4. check_itinerary on the result, then correct it.
""".strip()

mcp = MCPServer(
    name="reeltrip",
    title="ReelTrip trip planner",
    instructions=INSTRUCTIONS,
    website_url="https://reeltrip.onrender.com",
)


async def _in_thread(func, *args):
    """Run a blocking lookup without stalling the server's event loop."""
    return await anyio.to_thread.run_sync(lambda: func(*args))


@mcp.tool(title="Trending TikTok spots")
async def trending_spots(destination: str, month: str = "", interests: str = "") -> dict:
    """Places TikTok travellers recommend for a destination, verified on OpenStreetMap.

    Args:
        destination: A country, region or city, e.g. "Tunisia" or "Marrakech".
        month: Optional travel month, e.g. "December", to favour seasonal videos.
        interests: Optional interests, e.g. "food, desert, history".

    Returns spots ranked by how many videos mention them, each with coordinates,
    a one-line reason, and the TikTok video links it came from.
    """
    discovery = await _in_thread(social.trending_spots, destination, month, interests)
    return discovery.to_dict()


@mcp.tool(title="Places from TikTok links")
async def spots_from_tiktok_links(
    links: list[str], destination: str = "", captions: list[str] | None = None
) -> dict:
    """Map the places mentioned in TikTok posts the user saved.

    Args:
        links: Up to 10 TikTok video or photo-post URLs (short share links work).
        destination: Optional country or city, to keep only places located there.
        captions: Optional caption texts, for posts search engines haven't indexed.
    """
    discovery = await _in_thread(
        lambda: social.spots_from_links(links, destination, captions=captions)
    )
    return discovery.to_dict()


@mcp.tool(title="Verify a place")
async def verify_place(name: str, near: str = "") -> dict:
    """Check a place exists on OpenStreetMap and get its location.

    Args:
        name: The place, e.g. "Sidi Bou Said" or "Bardo Museum".
        near: Optional country or city to search within, e.g. "Tunisia".
    """
    place = await _in_thread(places.verify_place, name, near)
    if place is None:
        return {"found": False, "name": name, "note": "Not found on OpenStreetMap."}
    return {"found": True, **place.to_dict()}


@mcp.tool(title="Typical weather")
async def typical_weather(place: str, month: str) -> dict:
    """Typical highs, lows and rainy days for a place in a given month (°C).

    Based on last year's recorded weather for that month, not a forecast.
    """
    return await _in_thread(travel_info.typical_weather, place, month)


@mcp.tool(title="Prayer times")
async def prayer_times(place: str, date: str = "") -> dict:
    """Daily Islamic prayer times for a place, using the local calculation method.

    Args:
        place: City or town, e.g. "Kairouan".
        date: YYYY-MM-DD; defaults to today.
    """
    return await _in_thread(travel_info.prayer_times, place, date)


@mcp.tool(title="Getting there")
async def transfer_options(origin: str, destination: str) -> dict:
    """How to travel between two places: distance plus sourced train, bus,
    shared-taxi and flight information to summarise for the traveller."""
    return await _in_thread(travel_info.transfer_options, origin, destination)


@mcp.tool(title="Check an itinerary")
async def check_itinerary(
    itinerary: str,
    start_date: str = "",
    destination: str = "",
    halal: bool = False,
    ctx: Context | None = None,
) -> dict:
    """Check a day-by-day itinerary against the map and published opening days.

    Looks up every named place on OpenStreetMap near the town its day is set
    in, and reports: places with no trace on the map or the web (possibly
    invented), places far from that town (wrong place or long detour), sights
    scheduled on their weekly closing day, and days that cover too much
    distance or too many sights. Takes up to a minute.

    Args:
        itinerary: The full itinerary text, with its days and place names.
        start_date: First day of the trip as YYYY-MM-DD. Needed to match
            closing days to weekdays; leave empty if unknown.
        destination: Optional main city or country, e.g. "Tunis, Tunisia".
        halal: Also flag Fridays (midday prayer) and Ramadan for the traveller.

    Returns the findings ("issues", most serious first), per-place results
    ("stops"), counts ("summary"), and "share_url": a public page with the
    report on a map.
    """
    if not limits.spend("mcp", limits.MCP_CALLS_BUDGET):
        raise RuntimeError("ReelTrip's free daily capacity is used up. Please try again tomorrow.")
    try:
        start = _date.fromisoformat(start_date) if start_date else None
    except ValueError:
        start = None
    job = CheckJob(itinerary, start, halal, destination)
    async with anyio.create_task_group() as tg:
        tg.start_soon(anyio.to_thread.run_sync, job.run)
        reported = -1
        while job.status in ("queued", "running"):
            if ctx is not None and job.total and job.done != reported:
                reported = job.done
                await ctx.report_progress(job.done, job.total, job.label)
            await anyio.sleep(1)
    if job.status == "error":
        raise RuntimeError(job.error)
    storage.save("reviews", job.id, job.to_dict())
    report = job.report or {}
    return {
        "summary": report.get("summary"),
        "issues": report.get("issues"),
        "stops": [
            {k: s[k] for k in ("day", "name", "kind", "status", "where", "distance_km", "closed_days")}
            for s in report.get("stops", [])
        ],
        "notes": report.get("notes"),
        "share_url": f"{PUBLIC_URL.rstrip('/')}/c/{job.id}",
    }


async def plan_trip(
    origin: str,
    destinations: str,
    travel_dates: str,
    interests: str,
    inspiration: str = "",
    ctx: Context | None = None,
) -> str:
    """Run ReelTrip's seven-agent crew for a complete, verified itinerary.

    Takes several minutes. Only use it when the user asks for ReelTrip's own plan.

    Args:
        origin: Where the traveller starts, e.g. "Paris".
        destinations: Comma-separated candidate cities; the crew picks the best one.
        travel_dates: e.g. "10 December 2026 - 17 December 2026".
        interests: e.g. "food, history, desert".
        inspiration: Optional places the traveller wants considered, one per line.
    """
    job = PlanJob(origin, destinations, travel_dates, interests, inspiration)

    def run() -> None:
        # Keep CrewAI's console output off stdout, which carries the protocol.
        with contextlib.redirect_stdout(sys.stderr):
            job.run()

    async with anyio.create_task_group() as tg:
        tg.start_soon(anyio.to_thread.run_sync, run)
        reported = -1
        while job.status in ("queued", "running"):
            if ctx is not None and job.completed != reported:
                reported = job.completed
                await ctx.report_progress(job.completed, len(PHASES), job.phase)
            await anyio.sleep(2)

    if job.status == "error":
        raise RuntimeError(f"Planning failed: {job.error}")
    return job.result


# A full plan costs a minute of model time and a dozen searches, and the host
# assistant can write the plan itself. Offered only where the operator opts
# in (e.g. a private, local server).
if os.environ.get("VOYAGENT_MCP_PLAN_TRIP", "").lower() in ("1", "true", "yes"):
    mcp.tool(title="Full ReelTrip plan (slow)")(plan_trip)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ReelTrip as an MCP server.")
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.http:
        mcp.run("streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
