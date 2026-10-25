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
import sys

import anyio
from mcp.server.mcpserver import Context, MCPServer

from voyagent import places, social, travel_info
from voyagent.jobs import PHASES, PlanJob

INSTRUCTIONS = """
ReelTrip gives you grounded, verified travel data, with a focus on North Africa
and the Middle East (halal-friendly, prayer-time aware) but working worldwide.

Good workflow for a trip request:
1. trending_spots(destination, month) to see what travellers love on TikTok,
   or spots_from_tiktok_links(links) when the user shares videos they saved.
2. typical_weather and transfer_options to reality-check the ideas: distance,
   season, how to get there. Say plainly when a TikTok favourite is far away or
   a poor fit for the season.
3. verify_place before recommending any place you are unsure exists.
4. Build the itinerary yourself, grouping places by area. Cite the TikTok
   videos and sources the tools return.
Use plan_trip only when the user explicitly wants ReelTrip's own full plan;
it takes several minutes.
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
async def spots_from_tiktok_links(links: list[str], destination: str = "") -> dict:
    """Map the places mentioned in TikTok videos the user saved.

    Args:
        links: Up to 10 TikTok video URLs.
        destination: Optional country or city, to keep only places located there.
    """
    discovery = await _in_thread(social.spots_from_links, links, destination)
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


@mcp.tool(title="Full ReelTrip plan (slow)")
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
