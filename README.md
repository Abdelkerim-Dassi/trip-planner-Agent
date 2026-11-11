# TripCorrect

**The reality check for trip plans.** Live at **[reeltrip.onrender.com](https://reeltrip.onrender.com)**.

AI planners write confident itineraries with museums scheduled on the day they're closed, restaurants that are in another city, and places that don't exist. TripCorrect checks a plan against the real world and says exactly what it found.

Paste any itinerary (from ChatGPT, Gemini, a blog, or your own notes) and TripCorrect:

- **Looks up each named place on OpenStreetMap**, near the town that day is set in. A place with no trace on the map or the web is flagged as possibly invented.
- **Catches the wrong city.** A lunch "in Kairouan" that is really 135 km away, in Sidi Bou Said, is a problem; a sight that far is a long detour.
- **Matches sights to their weekly closing day** (OpenStreetMap's `opening_hours`, or published hours found by search, with the source) and flags a visit on a closed weekday.
- **Measures the day on real roads.** Driving time between a day's stops comes from OSRM routing, and days with more than two hours of road, or too many sights, are called out.
- **Knows the calendar.** Public holidays on your dates, sights that need tickets booked ahead, and, when asked, Friday prayer and Ramadan.
- **Fixes it in one click.** The plan is rewritten around the findings and the rewrite is checked again, so you see before and after ("3 problems → 0"). Or copy a **fix list to paste back into the assistant** that wrote the plan.
- Gives a **shareable report page** with a map, Google Maps links for each stop and each day's route, a link preview, and an optional "prepared by" name for travel advisors.

It reports in counts ("17 of 20 places found on the map, opening days checked for 6 of 11 sights"), never "everything verified". See a real report: [reeltrip.onrender.com/c/example](https://reeltrip.onrender.com/c/example).

TripCorrect also **plans**: it reads what travellers share on TikTok about a destination (or the TikTok links and captions you saved), keeps the places that are on the map, writes a day-by-day plan in English, French or Arabic, and then runs that plan through the same check. Halal food and prayer times on request.

And it works **inside Claude and ChatGPT** as an [MCP](https://modelcontextprotocol.io) server, so an assistant can check the itinerary it just wrote.

Free to run: Groq's and Gemini's free LLM tiers, Serper's free search tier (optionally Tavily's), and open data (OpenStreetMap, Open-Meteo, AlAdhan). Hosts free on Render.

## How the check works

`src/voyagent/review.py`. One small model call lists the places the text names, day by day. Everything after that is looked up, not generated:

| Step | Source | Finding |
|---|---|---|
| Is the place on the map near that day's town? | OpenStreetMap Nominatim, preferring matches in and around the town | found, far, or not on the map |
| If not on the map: does the web know it? | one exact-name web search | "online only" (probably real) or "no trace" (possibly invented) |
| Is a sight open on the scheduled weekday? | OSM `opening_hours`, else published hours read from search snippets (only when a snippet states them), cached for a month | closed-day conflict, with the source |
| Does the day fit? | driving time and road distance from OSRM (straight-line distance if routing is down); number of sights | long day, packed day |
| Public holidays, tickets | Nager.Date holidays for the country; a short list of sights known for timed tickets | notes |
| Friday and Ramadan | computed calendar (AlAdhan's Hijri calendar) | notes |

The best-known closing days (Louvre, Uffizi, Bardo and others) come from a sourced list in `closed_days.py`, so those are caught without a search; the same list is published at `/closed-days`.

A place of the same name but the wrong kind (a "Dar Zarrouk" that is a wine shop when the plan means a restaurant) is not accepted as a match. The pasted text is not stored; only the report is.

## How planning works

In production TripCorrect runs in **quick mode** (`src/voyagent/quick_plan.py`): code gathers the facts first (the traveller's TikTok spots, the computed trip calendar and Ramadan dates, typical weather, a few web searches, prayer times and halal-tagged places when asked) and one model call writes the plan under grounding and pacing rules. The plan is then checked by `review.py`; a sight scheduled on its closing day is moved by one editing call, and the report is shown under the plan.

**TikTok discovery** (`src/voyagent/social.py`) never scrapes TikTok or downloads videos. It searches Google's index of TikTok videos through Serper, has the model extract the places named in the captions, keeps the ones found on OpenStreetMap in the destination's country, and ranks them by how many videos mention them. Spots more than a day trip away are shown but left unticked.

A seven-agent [CrewAI](https://www.crewai.com/) crew (`crew.py`, `agents.py`, `tasks.py`) is still included for providers with larger limits (`VOYAGENT_PLAN_MODE=crew`); it is too token-hungry for the free tiers.

## Tech stack

- **Python 3.10/3.11**, `pip` or Poetry
- **FastAPI + Uvicorn** for the web app and JSON API; plain HTML/CSS/JS front end (no build step) with **Leaflet** maps on OpenStreetMap tiles
- **LiteLLM** (via `crewai[litellm]`) for Groq, Gemini and OpenAI
- **MCP Python SDK** (`mcp` 2.x) for the Claude / ChatGPT integration
- **Serper.dev** (and optionally **Tavily**) for web search; **OpenStreetMap Nominatim / Overpass**, **Open-Meteo** and **AlAdhan** for free grounded data
- **Upstash Redis** (free) for reports, plans, caches and daily limits
- **Docker** for hosting (Render's free plan, or any container host)

## Repository structure

```
.
├── src/voyagent/
│   ├── review.py             # The itinerary check: map, wrong city, closing days, day load
│   ├── hours.py              # Weekly closing days from OSM or published hours
│   ├── closed_days.py        # Sourced closing days of famous sights (check + /closed-days page)
│   ├── routes.py             # Driving time between a day's stops (OSRM)
│   ├── holidays.py           # Public holidays (Nager.Date)
│   ├── stats.py              # Usage counts without a tracker (/stats)
│   ├── places.py             # OpenStreetMap place lookup (city-aware, cached)
│   ├── quick_plan.py         # One grounded call that writes a plan (free tiers)
│   ├── social.py             # TikTok discovery: captions -> places on the map
│   ├── jobs.py               # Background plan and check jobs with progress
│   ├── limits.py             # Daily per-visitor limits and global budgets
│   ├── serper.py             # Web search: saved cache, daily budget, Tavily option
│   ├── storage.py            # Upstash Redis (free) or local files
│   ├── travel_info.py        # Typical weather, prayer times, Ramadan, transfers
│   ├── share_images.py       # Link preview cards and the post carousel (Pillow)
│   ├── content.py            # Caption, hashtags and voice-over for a plan
│   ├── exports.py            # .ics calendar export
│   ├── plan_text.py          # Reads a plan's day sections and items
│   ├── llm.py                # Model calls that ride out free-tier limits
│   ├── config.py             # Env loading, provider/model selection
│   ├── mcp_server.py         # TripCorrect MCP server (stdio or HTTP)
│   ├── crew.py, agents.py, tasks.py, tools/   # The optional seven-agent crew
│   └── web/                  # FastAPI app, page templates, static JS/CSS, example report
├── tests/                    # Offline tests (pytest)
├── scripts/launch_check.py   # End-to-end live check of a running instance
├── Dockerfile                # Container for Render / any host
├── docs/                     # Project documentation and the launch kit
├── .env.example              # Template for API keys and limits
├── requirements.txt          # pip dependencies (used by the Dockerfile)
└── pyproject.toml            # Poetry project + dependencies
```

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/Abdelkerim-Dassi/trip-planner-Agent.git
cd trip-planner-Agent
pip install -r requirements.txt
```

### 2. Configure API keys

Copy `.env.example` to `.env` and fill it in. `SERPER_API_KEY` is always required; the LLM key depends on the provider.

**Free setup (what the live site runs):**

```env
VOYAGENT_PROVIDER=groq
GROQ_API_KEY=gsk_...          # free at https://console.groq.com/keys
GEMINI_API_KEY=...            # free at https://aistudio.google.com (fallback when Groq is busy)
SERPER_API_KEY=...            # free tier at https://serper.dev
TAVILY_API_KEY=...            # optional, free 1,000 searches a month at https://tavily.com
```

With `TAVILY_API_KEY` set, searches that don't need Google's TikTok index go to Tavily first, which saves Serper credits. The Tavily path is written against Tavily's documented API and covered by offline tests, but has not been run against the live service yet.

### 3. Run the web app

```bash
python -m voyagent.web            # http://127.0.0.1:8000
```

- **Check an itinerary:** paste a plan, add the first day of the trip (needed to match closing days to weekdays), and read the report. **Fix it for me** rewrites the plan and checks the rewrite. Finished reports live at `/c/<id>`. `/check/chatgpt`, `/check/gemini`, `/check/claude`, `/check/copilot` and `/check/perplexity` are the same page worded for each assistant.
- **Plan from TikTok:** fill in where and when. With **Inspired by TikTok** on (or links pasted) TripCorrect first shows the spots travellers love on a map; untick what you'd skip and build the plan. Finished plans live at `/p/<id>`, with a calendar export and a **Post this trip** page.

The JSON API is documented at `/api/docs`.

### 4. Run the tests

```bash
python -m pytest tests -q
```

### 5. Use TripCorrect from Claude or ChatGPT (MCP)

Tools: `check_itinerary`, `trending_spots`, `spots_from_tiktok_links`, `verify_place`, `typical_weather`, `prayer_times`, `transfer_options`. (`plan_trip`, the full planner, is registered only when `VOYAGENT_MCP_PLAN_TRIP=1`, for private servers.)

**Remote (Claude custom connector, ChatGPT apps):** the web app serves the MCP server at `https://<your-host>/mcp` (the official one is `https://reeltrip.onrender.com/mcp`). Add that URL as a custom connector.

**Claude Desktop (local):** add this to `claude_desktop_config.json`, then restart Claude:

```json
{
  "mcpServers": {
    "tripcorrect": {
      "command": "python",
      "args": ["-m", "voyagent.mcp_server"],
      "env": {
        "PYTHONPATH": "C:/path/to/trip-planner-Agent/src",
        "VOYAGENT_PROVIDER": "groq",
        "GROQ_API_KEY": "gsk_...",
        "SERPER_API_KEY": "..."
      }
    }
  }
}
```

## Deploying for free (Render)

Render's free plan runs the `Dockerfile` with no credit card. Without a card on file, Render pauses the service if you exceed the free limits instead of billing you.

1. Sign up at [render.com](https://render.com).
2. **New → Web Service → Public Git Repository**, and enter this repo's GitHub URL.
3. Render detects the `Dockerfile`. Pick a region close to your users, set **Instance Type** to **Free**, and leave the start command empty.
4. Under **Environment Variables**, add `VOYAGENT_PROVIDER=groq`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `SERPER_API_KEY`, and optionally `TAVILY_API_KEY` and `VOYAGENT_SUPPORT_URL`.
5. **Keep share links working:** create a free Redis database at [upstash.com](https://upstash.com) (no card), open its **REST API** section, and add `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`. `/healthz` then shows `"plans_persist": true`. The same database keeps the search cache and the daily limits across restarts.
6. **Deploy.** When the repo is connected by public URL, Render does not deploy on push: after pushing, use **Manual Deploy → Deploy latest commit**.

Free-plan limits: the service sleeps after 15 minutes without traffic and takes about a minute to wake (the scheduled workflow in `.github/workflows/health.yml` requests `/healthz` every 10 minutes, which keeps it awake and fits the 750 free hours); its disk is wiped on every restart, so without Upstash shared links break; and it has 512 MB of memory.

## Configuration

Set in `.env` or the host's environment.

| Variable | Purpose | Default |
|---|---|---|
| `VOYAGENT_PROVIDER` | `openai`, `groq` or `gemini` | `openai` |
| `VOYAGENT_MODEL` | model name | `gpt-4o-mini` (openai) / `openai/gpt-oss-120b` (groq) |
| `VOYAGENT_PLAN_MODE` | `quick` (one grounded call) or `crew` (7 agents) | `quick` on groq, else `crew` |
| `VOYAGENT_FALLBACK_MODEL` | free model used when the primary is rate-limited (`""` disables) | Gemini Flash when `GEMINI_API_KEY` is set |
| `VOYAGENT_DISCOVERY_MODEL` | model for the fast steps (reading an itinerary, TikTok captions, opening hours during a check) | the main model |
| `VOYAGENT_HELPER_MODEL` | model for small background jobs (captions) | the fallback model, else the discovery model |
| `TAVILY_API_KEY` | second search provider for non-TikTok searches | unset |
| `VOYAGENT_DAILY_CHECKS_PER_IP` | itinerary checks per visitor per day | `12` |
| `VOYAGENT_DAILY_PLANS_PER_IP` | plans per visitor per day | `6` |
| `VOYAGENT_DAILY_DISCOVERS_PER_IP` | TikTok discoveries per visitor per day | `12` |
| `VOYAGENT_DAILY_SEARCH_BUDGET` | Serper searches per day, everyone together | `200` |
| `VOYAGENT_DAILY_MCP_BUDGET` | itinerary checks per day through MCP | `300` |
| `VOYAGENT_MAX_ACTIVE_PLANS` / `VOYAGENT_MAX_ACTIVE_CHECKS` | jobs allowed at once | `2` / `3` |
| `VOYAGENT_MCP_PLAN_TRIP` | `1` registers the slow `plan_trip` MCP tool | off |
| `VOYAGENT_STATS_KEY` | a secret word that turns on the usage page at `/stats?key=<word>` | unset (page hidden) |
| `VOYAGENT_ROUTING_URL` | OSRM server for driving times (`""` turns routing off) | OSRM's public demo server |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | free Redis for reports, plans, caches and limits | unset (local files only) |
| `VOYAGENT_PUBLIC_URL` | site address used in link previews and share links | the request's address (Render's is detected) |
| `VOYAGENT_PUBLIC_HOSTS` | extra hostnames the `/mcp` endpoint accepts | unset |
| `VOYAGENT_SUPPORT_URL` | donation page shown after a plan and in the footer | unset |
| `VOYAGENT_CONTACT_URL` | where "Report a problem" points | this repo's issues |
| `VOYAGENT_LANGUAGE` | language for place names from OpenStreetMap | `en` |
| `VOYAGENT_DATA_DIR` | local copy of reports, plans and caches | `data` |

See [docs/launch/](docs/launch/README.md) for the launch kit.

## What the check can't do

It looks places up on OpenStreetMap and reads published opening hours. It can miss a real place (especially one mapped under a local name), match the wrong one, or rely on hours that have changed. It can't see strikes, renovations, sold-out tickets or prices. It is a second pair of eyes, not a guarantee.

## License

Personal / educational project.

TripCorrect was called ReelTrip until November 2026 and Voyagent before that. The Python package and settings keep the original name (`voyagent`, `VOYAGENT_*`) so existing setups keep working, and the live address still carries the earlier name until the service is recreated under the new one.
