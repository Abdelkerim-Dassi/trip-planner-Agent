# Voyagent

A multi-agent AI travel planner built on [CrewAI](https://www.crewai.com/). Give it an origin, candidate destinations, dates and interests, and seven specialized agents pick the best city, research it, and return a verified day-by-day itinerary with logistics, budget and packing notes.

What makes it different:

- **TikTok to trip plan.** Voyagent reads what travellers share on TikTok about your destination, or the TikTok links you saved, pulls out the places they mention, keeps only the ones OpenStreetMap confirms exist, and puts them on a map. You keep the ones you like and the crew builds them into your plan, with a travel agent's reality check (distance, season, crowds).
- **Works inside Claude and ChatGPT.** Voyagent is also an [MCP](https://modelcontextprotocol.io) server with grounded tools: trending TikTok spots, place verification, typical weather, prayer times and getting-there options.
- **Free to run.** Groq's free LLM tier (or OpenAI), Serper's free search tier, and free open data (OpenStreetMap, Open-Meteo, AlAdhan). Hosts free on Render.

## How it works

Seven CrewAI agents run in sequence. Each step's output is passed forward as task **context**, so every agent works from the verified result of the one before:

| # | Agent | What it does |
|---|---|---|
| 1 | **City Selection Expert** | Picks the best city **from your candidates** for the dates and interests (weather, events, prices). |
| 2 | **Local Expert** | Builds a guide: attractions, neighbourhoods, customs, food, events. |
| 3 | **Experience Curator** | Surfaces signature experiences and hidden gems, and weighs the TikTok spots you kept. |
| 4 | **Travel Concierge** | Drafts the day-by-day plan for your exact dates, with weather, packing list and budget. |
| 5 | **Logistics Planner** | Adds getting around, transfers and booking notes. |
| 6 | **Itinerary Critic** | Fixes pacing, geography and gaps. |
| 7 | **Final Editor** | Polishes the verified plan into one document (no new facts allowed). |

Every agent must ground claims in web search: only real places in the selected country, links only when copied from a result, °C, one currency. The model is provider-switchable in `src/voyagent/config.py`: OpenAI `gpt-4o-mini` by default, or Groq's free tier with `VOYAGENT_PROVIDER=groq`.

**TikTok discovery** (`src/voyagent/social.py`) never scrapes TikTok or downloads videos. It searches Google's index of TikTok videos through Serper, has the LLM extract the places named in the captions, verifies each with OpenStreetMap's Nominatim (in the destination's country only), and ranks them by how many videos mention them. Every spot links back to its videos.

## Tech stack

- **Python 3.10/3.11**, `pip` or Poetry
- **CrewAI** (`crewai[litellm]`) for the agents; LiteLLM for Groq
- **FastAPI + Uvicorn** for the web app and JSON API; plain HTML/CSS/JS front end (no build step) with **Leaflet** maps on OpenStreetMap tiles
- **MCP Python SDK** (`mcp` 2.x) for the Claude / ChatGPT integration
- **Serper.dev** for web search; **OpenStreetMap Nominatim**, **Open-Meteo** and **AlAdhan** for free grounded data
- **Docker** for hosting (Render's free plan, or any container host)

## Repository structure

```
.
├── src/voyagent/
│   ├── __main__.py           # CLI entry point (python -m voyagent)
│   ├── crew.py               # TripCrew: orchestration, context wiring, Groq throttle/retry
│   ├── agents.py             # The 7 agent definitions
│   ├── tasks.py              # Task prompts with grounding rules
│   ├── config.py             # Env loading, provider/model selection, key validation
│   ├── jobs.py               # Background plan jobs + progress phases (web + MCP)
│   ├── social.py             # TikTok discovery: captions -> verified, ranked spots
│   ├── places.py             # OpenStreetMap place verification and distances
│   ├── travel_info.py        # Typical weather, prayer times, transfer options
│   ├── serper.py             # Shared Serper search client (cached)
│   ├── mcp_server.py         # Voyagent MCP server (stdio or HTTP)
│   ├── tools/                # CrewAI tools: web search, calculator
│   └── web/                  # FastAPI app, page templates, static JS/CSS
├── Dockerfile                # Container for Render / any host
├── docs/                     # Project documentation
├── .env.example              # Template for required API keys
├── requirements.txt          # pip dependencies (used by the Dockerfile)
└── pyproject.toml            # Poetry project + dependencies
```

## Getting started

### 1. Clone

```bash
git clone https://github.com/Abdelkerim-Dassi/trip-planner-Agent.git
cd trip-planner-Agent
```

### 2. Install dependencies (Poetry recommended)

```bash
poetry install
poetry shell
```

Or with pip:

```bash
pip install -r requirements.txt
```

### 3. Configure API keys

Copy `.env.example` to `.env` and fill it in. `SERPER_API_KEY` is always required; the LLM key depends on the provider you choose.

```bash
cp .env.example .env
```

**Free, with Groq (recommended for trying it out):**

```env
VOYAGENT_PROVIDER=groq
GROQ_API_KEY=gsk_...          # free at https://console.groq.com/keys
SERPER_API_KEY=...            # free tier at https://serper.dev
```

**With OpenAI (default provider):**

```env
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
```

The app validates these at startup and fails fast with a clear message if a required key is missing.

### 4. Run the CLI

```bash
python -m voyagent
# or, after `poetry install`:
voyagent
```

You'll be prompted for four inputs:

```
Enter origin: Tunis
Enter candidate destinations (comma-separated): Lisbon, Porto, Barcelona
Enter travel time range: 15 June - 22 June
Enter interests: food, architecture, beach
```

The crew runs and the final trip plan prints to the terminal.

### 5. Run the web app

```bash
python -m voyagent.web            # http://127.0.0.1:8000
```

Fill in the trip form. With **Inspired by TikTok** on (or links pasted), Voyagent first shows the spots travellers love on a map, in about 30 seconds per destination. Untick what you'd skip, click **Build my itinerary**, and follow the crew's progress phase by phase. The finished plan has a **share link** (`/p/<id>`, a server-rendered page that previews well on social media), Markdown download and print-to-PDF.

The JSON API is documented at `/api/docs`.

### 6. Use Voyagent from Claude or ChatGPT (MCP)

Voyagent's MCP tools: `trending_spots`, `spots_from_tiktok_links`, `verify_place`, `typical_weather`, `prayer_times`, `transfer_options`, and `plan_trip` (the full crew; slow).

**Claude Desktop (local):** add this to `claude_desktop_config.json`, then restart Claude:

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

**Remote (Claude custom connector, ChatGPT apps):** the web app serves the same MCP server at `https://<your-host>/mcp`. Deploy it (below), then add that URL as a custom connector in Claude, or as a connector in ChatGPT's developer mode. To run only the MCP server over HTTP: `python -m voyagent.mcp_server --http --port 8000`.

## Deploying for free (Render)

Render's free plan runs the `Dockerfile` with no credit card. Without a card on file, Render pauses the service if you exceed the free limits instead of billing you.

1. Sign up at [render.com](https://render.com) (signing in with GitHub is easiest).
2. In the dashboard click **New → Web Service**, choose **Public Git Repository** and enter this repo's GitHub URL (or connect your GitHub account and pick the repo).
3. Render detects the `Dockerfile`. Pick a region close to your users, set **Instance Type** to **Free**, and leave the start command empty.
4. Under **Environment Variables**, add `SERPER_API_KEY` and either `GROQ_API_KEY` (plus `VOYAGENT_PROVIDER=groq`) or `OPENAI_API_KEY`. Optionally add `VOYAGENT_SUPPORT_URL` with your Ko-fi or GitHub Sponsors page to show a "Support Voyagent" link.
5. Click **Deploy Web Service**. The first build takes several minutes. The app is then live at `https://<service-name>.onrender.com`, and the MCP endpoint at `https://<service-name>.onrender.com/mcp`.

Free-plan limits: the service sleeps after 15 minutes without traffic and takes about a minute to wake; its disk is wiped on every restart or redeploy, so shared plan links don't last; and it has 512 MB of memory, which is tight for a full crew run. The same `Dockerfile` also runs on any other container host.

## Example output

A typical run produces:

- A picked city (from the candidates) with justification: weather for the dates, prices, fit to interests
- A local guide: top attractions, neighborhoods, local customs, seasonal events
- A day-by-day itinerary **covering your exact travel dates**: activities, real hotels and restaurants
- A budget table in one consistent currency
- A packing list tailored to the weather

## Configuration

The provider and model are configured in one place — `src/voyagent/config.py` — and overridable via environment variables (no code change):

| Variable | Purpose | Default |
|---|---|---|
| `VOYAGENT_PROVIDER` | `openai` or `groq` | `openai` |
| `VOYAGENT_MODEL` | model name | `gpt-4o-mini` (openai) / `llama-3.3-70b-versatile` (groq) |
| `VOYAGENT_TEMPERATURE` | sampling temperature | `0.2` |
| `GROQ_STEP_DELAY_SECONDS` | pace agent steps under Groq's free TPM cap (`0` to disable) | `10` |
| `GROQ_NUM_RETRIES` | retries when Groq returns a rate-limit 429 | `8` |
| `CREW_MAX_ATTEMPTS` | retries of the whole crew on Groq's transient tool-call error | `3` |
| `VOYAGENT_MAX_ACTIVE_PLANS` | crew runs allowed at once in the web app (others get "busy, try again") | `2` |
| `VOYAGENT_SUPPORT_URL` | donation page shown after a plan and in the footer (hidden if unset) | unset |
| `VOYAGENT_DATA_DIR` | where finished plans are saved for share links | `data` |
| `VOYAGENT_PUBLIC_HOSTS` | extra hostnames the `/mcp` endpoint accepts, comma-separated (Render's `RENDER_EXTERNAL_HOSTNAME` is added automatically) | unset |
| `VOYAGENT_LANGUAGE` | language for place names from OpenStreetMap | `en` |

See [docs/configuration.md](docs/configuration.md) for adding tools and tuning behavior, and [docs/](docs/README.md) for the full documentation set.

> **Note on Groq's free tier:** it caps tokens per minute (≈12k) and per day (≈100k). Voyagent paces and retries calls to stay within the per-minute limit, but a full plan is token-heavy, so the free tier allows only a few runs per day. For faster, higher-volume use, switch `VOYAGENT_MODEL` to a lighter model or upgrade to Groq's Dev tier (and set `GROQ_STEP_DELAY_SECONDS=0`).

## License

Personal / educational project.
