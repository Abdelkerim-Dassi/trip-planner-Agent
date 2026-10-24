# Usage

Voyagent runs three ways: an interactive **CLI**, a **web app** (FastAPI), and an **MCP
server** for Claude, ChatGPT and other assistants. All of them drive the same `TripCrew`.

## CLI

From the project root (inside your Poetry/venv shell):

```bash
python -m voyagent
# or, after `poetry install`, the console script:
voyagent
```

The CLI first validates your API keys, then prompts for four inputs:

| Prompt | Meaning | Example |
|---|---|---|
| `Enter origin:` | The city you are departing from | `Tunis` |
| `Enter candidate destinations (comma-separated):` | One or more candidate cities | `Lisbon, Porto, Barcelona` |
| `Enter travel time range:` | The date window for the trip | `15 June - 22 June` |
| `Enter interests:` | Themes to optimize the trip around | `food, architecture, beach` |

The City Selection Expert picks **one** city from the candidate list (never the origin), and
the rest of the seven-agent crew plans for that city. When the run finishes, the final trip
plan prints to the terminal:

```
########################
## Here is your Trip plan:
########################

<markdown trip plan>
```

The crew runs with `verbose=False`, so the agents' internal reasoning is not dumped to the
console — you get progress from CrewAI plus the final plan. The CLI does not run TikTok
discovery; that is part of the web app and the MCP tools.

## Web app

```bash
python -m voyagent.web            # http://127.0.0.1:8000
# options: --host 0.0.0.0 --port 7860 --reload   (or set HOST / PORT)
# after `poetry install`: voyagent-web
```

- Fill in **where from**, **where to** (one or more comma-separated places), the **dates**
  (two date pickers), and **what you love**.
- **Inspired by TikTok** (on by default) and/or pasted TikTok links: Voyagent first shows the
  spots travellers love on a **Leaflet map**, in about 30 seconds per destination (up to 3
  destinations). Every spot is confirmed on OpenStreetMap and links back to its videos. Untick
  what you'd skip, then click **Build my itinerary**; the spots you keep are passed to the
  Experience Curator, which adds a reality check (distance, season, crowds) for each.
- While the crew works, a **7-phase progress bar** shows friendly status — *Choosing your
  destination → Researching the city → Uncovering hidden gems → Crafting your itinerary →
  Sorting out the logistics → Refining every detail → Polishing your plan* — and never the raw
  agent reasoning.
- The finished plan offers a **share link** (`/p/<id>`, a server-rendered page that previews
  well on social media), **Download** as Markdown (`voyagent-trip-plan.md`), and
  **Print / PDF**.

At most `VOYAGENT_MAX_ACTIVE_PLANS` (default 2) crew runs happen at once; further requests get
a "busy, try again" message. If `VOYAGENT_SUPPORT_URL` is set, a support link is shown after
the plan and in the footer.

### JSON API

The same endpoints the page uses are documented (OpenAPI) at `/api/docs`:

| Endpoint | Body / result |
|---|---|
| `POST /api/discover` | `{destinations, month, interests, links}` → `{results: [...]}` (spots, videos, unverified names, notes) |
| `POST /api/plans` | `{origin, cities, start, end, interests, inspiration}` (dates as `YYYY-MM-DD`) → `202` with the job |
| `GET /api/plans/{id}` | `{id, status, phase, completed, total, steps, result, error, request}` |
| `GET /healthz` | `{ok: true}` |

Poll `GET /api/plans/{id}` until `status` is `done` (or `error`).

### Hosting

The `Dockerfile` runs the web app on port 7860, ready for Hugging Face Spaces (Docker SDK,
free CPU tier) or any container host (Render, Koyeb, Railway, ...). See the root
[README](../README.md#deploying-for-free-hugging-face-spaces) for the Space header and the
secrets to set. Free Spaces sleep when idle and their disk is not persistent, so shared plan
links last only until the Space restarts.

## MCP server (Claude, ChatGPT)

Voyagent's MCP tools:

| Tool | What it returns |
|---|---|
| `trending_spots(destination, month, interests)` | TikTok-recommended places, verified on OpenStreetMap, ranked by video mentions |
| `spots_from_tiktok_links(links, destination)` | Places mentioned in up to 10 TikTok videos the user saved |
| `verify_place(name, near)` | Whether a place exists on OpenStreetMap, and where |
| `typical_weather(place, month)` | Typical highs/lows/rainy days (°C), from last year's records |
| `prayer_times(place, date)` | Daily Islamic prayer times using the local calculation method |
| `transfer_options(origin, destination)` | Straight-line distance plus sourced train/bus/shared-taxi/flight info |
| `plan_trip(origin, destinations, travel_dates, interests, inspiration)` | The full seven-agent plan (slow; several minutes) |

The server's instructions tell the assistant to use the fast lookups and build the itinerary
itself, and to call `plan_trip` only when the user explicitly wants Voyagent's own plan.

**Claude Desktop (local, stdio):** add this to `claude_desktop_config.json`, then restart
Claude:

```json
{
  "mcpServers": {
    "voyagent": {
      "command": "python",
      "args": ["-m", "voyagent.mcp_server"],
      "env": {
        "PYTHONPATH": "C:/path/to/trip-planner-Agent/src",
        "SERPER_API_KEY": "...",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

For Groq, use `"VOYAGENT_PROVIDER": "groq"` and `"GROQ_API_KEY"` instead of the OpenAI key.

**Remote (Claude custom connector, ChatGPT apps):** the web app serves the same MCP server at
`https://<your-host>/mcp`. Deploy it, then add that URL as a custom connector in Claude, or as
a connector in ChatGPT's developer mode. On hosts other than Hugging Face Spaces (which sets
`SPACE_HOST` automatically), add your hostname to `VOYAGENT_PUBLIC_HOSTS` so the endpoint
accepts it.

To run only the MCP server over HTTP:

```bash
python -m voyagent.mcp_server --http --port 8000   # serves /mcp; --host defaults to 127.0.0.1
# after `poetry install`: voyagent-mcp [--http]
```

## Expected output

A typical crew run produces a markdown plan containing:

- **Chosen city** (from your candidates) with justification (weather for the dates, prices, fit)
- **Local guide** — top attractions, neighborhoods, customs, seasonal events
- **Signature experiences and hidden gems**, including the TikTok spots you kept (with a
  reality check)
- **Day-by-day itinerary** covering **exactly your travel dates** (not a fixed length): daily
  activities, specific hotels and restaurants
- **Getting around** — transit options, passes, transport between stops, book-ahead flags
- **Weather** summary in °C
- **Budget table** in one consistent currency
- **Packing list** tailored to the weather

Because the prompts force grounding in search results, the model omits details it can't verify
(e.g. it will skip a link rather than guess one), and the Final Editor may not add new facts.

## Tips

- A full plan runs seven agents with multiple LLM calls and many web searches, so it takes
  several minutes — longer on Groq's free tier because steps are paced to respect the rate
  limit.
- On Groq's free tier you only get a few full runs per day (token cap). For more, switch to a
  lighter `VOYAGENT_MODEL`, or upgrade the Groq tier and set `GROQ_STEP_DELAY_SECONDS=0`.
- Give specific, comma-separated interests for sharper recommendations.
- To save CLI output: `python -m voyagent | tee trip-plan.md`.
