# Agents, Tasks & Tools reference

A per-component reference for the `voyagent` package.

## Configuration — `config.py`

The single source of truth for environment, provider, and model setup.

- `PROVIDER` — `"openai"` (default) or `"groq"`, from `VOYAGENT_PROVIDER`.
- `MODEL_NAME` — chat model; defaults to `gpt-4o-mini` (openai) or `llama-3.3-70b-versatile`
  (groq); override with `VOYAGENT_MODEL`.
- `MODEL_TEMPERATURE` — sampling temperature (default `0.2`; override with `VOYAGENT_TEMPERATURE`).
- `REQUIRED_KEYS` — `SERPER_API_KEY` plus the provider's key (`OPENAI_API_KEY` or `GROQ_API_KEY`).
- `validate_env()` — raises `MissingConfigError` listing any missing required keys.
- `build_llm()` — returns the shared model: a `ChatOpenAI` for openai, or a `crewai.LLM`
  (`groq/<model>`, with `num_retries`) for groq. Imports are lazy so config-only use needs
  neither `langchain` nor `crewai`.
- `litellm_model()` — the configured model as a LiteLLM model id (`groq/<model>` on Groq, the
  bare model name otherwise), for one-off completions outside the crew (TikTok place
  extraction).

## Agents — `agents.py`

The `TravelAgents` class builds the shared LLM once in `__init__` and exposes seven factory
methods, each returning a configured CrewAI `Agent`. All agents set `allow_delegation=False`
and `verbose=False`, and `max_iter=10` (`_MAX_ITER`) except the Final Editor (`max_iter=3`).
Goals and backstories stress verified, local-only information.

### `city_selection_agent()`
- **role:** City Selection Expert
- **goal:** Pick the single best city from the candidate list using only facts found via search
- **tools:** `SearchTools.search_internet`, `CalculatorTool.calculate`

### `local_expert()`
- **role:** Local Expert at this city
- **goal:** Describe the selected city accurately using only verified, local information
- **tools:** `SearchTools.search_internet`

### `experience_curator()`
- **role:** Local Experience Curator
- **goal:** Surface the signature experiences and hidden gems a typical tourist would miss,
  matched to the traveller's interests and verified by search
- **tools:** `SearchTools.search_internet`

### `travel_concierge()`
- **role:** Amazing Travel Concierge
- **goal:** Turn the city guide into an accurate itinerary, weather, packing list, and budget
- **tools:** `SearchTools.search_internet`, `CalculatorTool.calculate`

### `logistics_planner()`
- **role:** Travel Logistics Planner
- **goal:** Make the itinerary easy to follow: transport between stops, transit passes,
  what to book in advance, sensible timing — verified for this city
- **tools:** `SearchTools.search_internet`, `CalculatorTool.calculate`

### `itinerary_critic()`
- **role:** Meticulous Itinerary Critic
- **goal:** Return a corrected plan: every place real and in the right city, geographic flow,
  realistic pacing, day count matching the dates exactly
- **tools:** `SearchTools.search_internet`, `CalculatorTool.calculate`

### `final_editor()`
- **role:** Travel Storyteller and Editor
- **goal:** Polish the verified plan into one cohesive document without adding any new facts,
  places, links, or numbers
- **tools:** none (`max_iter=3`)

## Tasks — `tasks.py`

The `TravelTasks` class exposes seven task factories. Each returns a CrewAI `Task` whose
`description` is a templated prompt with an `expected_output`. A shared `_GROUNDING_RULES`
block is injected into every prompt except `polish_plan` (verify via search; real in-country
places only; links copied verbatim from results only — never guessed; omit unverifiable
details; write only for the traveller). `polish_plan` uses `_EDITING_RULES` (no search tool;
no new places, links, prices, dates, or weather figures; keep all substance). A private
`__tip_section()` appends a "$10,000 commission" incentive line to every task.

### `identify_city(agent, origin, cities, travel_dates, interests)`
- **Purpose:** Recommend **one** city chosen only from `cities` (never the origin).
- **expected_output:** The selected city plus a short justification (weather for the dates,
  approximate flight cost, fit to interests).

### `gather_city_info(agent, travel_dates, interests, context=None)`
- **Purpose:** Compile an in-depth guide for the **selected** city (read from `context`, which
  is set to `[identify_city]` by the crew).
- **expected_output:** A guide to the selected city — attractions, neighborhoods, customs, local
  food, and events during the dates, all verified via search.

### `curate_experiences(agent, travel_dates, interests, context=None, inspiration="")`
- **Purpose:** Curate 5–8 signature experiences and hidden gems from the guide
  (`context=[gather_city_info]`). When `inspiration` is non-empty, `_inspiration_section()`
  adds the traveller's own places (e.g. kept TikTok spots, already confirmed on
  OpenStreetMap): include those that fit the city and season with a reality check (travel time,
  worth it this season, best time to avoid crowds), and say in one line why any are skipped.
- **expected_output:** A shortlist of 5–8 experiences, each with name, neighbourhood, why it
  stands out, and an ideal time — all verified and in the selected city.

### `plan_itinerary(agent, travel_dates, interests, context=None)`
- **Purpose:** Expand the guide and curated experiences
  (`context=[gather_city_info, curate_experiences]`) into a day-by-day itinerary covering
  **exactly** the travel dates.
- **expected_output:** A complete markdown plan that starts directly with the plan: per-day
  schedule for the exact dates, weather in °C, packing list, and a budget table in one
  consistent currency.

### `add_logistics(agent, travel_dates, context=None)`
- **Purpose:** Return the same plan (`context=[plan_itinerary]`) with logistics woven in.
- **expected_output:** The complete itinerary plus a Getting Around section, transport notes
  between stops, transit-pass advice, and advance-booking flags.

### `critique_itinerary(agent, travel_dates, context=None)`
- **Purpose:** Fix the plan (`context=[add_logistics]`) and return it whole, not as notes.
- **expected_output:** The corrected plan: verified places, geographic flow, realistic pacing,
  one entry per travel day, consistent currency and a budget that adds up.

### `polish_plan(agent, context=None)`
- **Purpose:** Reshape the corrected plan (`context=[critique_itinerary]`) into the final
  document, opening with a short evocative intro.
- **expected_output:** A polished markdown plan — intro, per-day schedule, getting around,
  signature experiences, weather, packing list, budget — with no new facts.

> The itinerary length follows the dates (no fixed "7-day" wording). The `city` parameter is
> not passed to downstream tasks; the selected city flows through `context`.

## Tools — `tools/`

### `SearchTools.search_internet(query)` — `search_tools.py`
- Decorated with `@tool("Search the internet")`.
- Calls `serper.search(query)` (see below) and returns a friendly message instead of raising
  when the key is missing or the request fails.
- Returns the top **2** organic results (`TOP_RESULTS_TO_RETURN`), each as Title / Link /
  Snippet, with snippets truncated to `MAX_SNIPPET_CHARS` (150) — kept small to limit token use
  on rate-limited free tiers.

### `CalculatorTool.calculate(operation)` — `calculator_tools.py`
- Decorated with `@tool("Make a calculation")`.
- Evaluates a math expression string (e.g. `'200*7'`) with a **restricted AST evaluator** — only
  numeric literals and arithmetic operators (`+ - * / // % **`, unary `+/-`) are allowed, so
  arbitrary code cannot be executed.
- Handles division-by-zero and invalid/unsupported expressions with friendly messages.

## Search client — `serper.py`

- `search(query) -> list[dict]` — Serper.dev Google Search (`https://google.serper.dev/search`)
  with a 15-second timeout; returns the organic results (`title`, `link`, `snippet`).
- Results are cached per query for the life of the process (`lru_cache`, 512 entries), which
  saves credits when several users explore the same destination.
- Raises `SearchError` when `SERPER_API_KEY` is unset, the request fails, or Serper rejects it
  (its `message` is included). Free of `crewai` so the web app and MCP server import it cheaply.

## Place verification — `places.py`

Uses OpenStreetMap's Nominatim geocoder (free, no key) and follows its usage policy: requests
are spaced ~1.1 s apart across all threads, sent with an identifying `User-Agent`
(`VOYAGENT_USER_AGENT`), and cached.

- `Place` — frozen dataclass: `name`, `display_name`, `lat`, `lon`, `country_code`, `kind`
  (Nominatim address type), `osm_url`, `category`, `osm_type`; `is_city`, `to_dict()`.
- `geocode(query, country_code="") -> Place | None` — first match, optionally restricted to one
  country; names in `VOYAGENT_LANGUAGE` (default `en`). Cached (2048 entries).
- `verify_place(name, near="") -> Place | None` — resolves `near`'s country, then tries the
  bare name in that country, then `"name, near"`.
- `distance_km(a, b)` — great-circle distance in kilometres.

## TikTok discovery — `social.py`

Never scrapes TikTok or downloads videos. Pipeline:

1. Search Google's index of TikTok videos through Serper (`site:tiktok.com <destination>`
   with "places to visit", "hidden gems", and the month or interests — up to 3 queries).
2. Ask the LLM (LiteLLM, `config.litellm_model()`, JSON mode, `temperature=0`) to list only the
   places explicitly named in the captions, with a one-line "why" and the videos mentioning each.
3. Rank by how many distinct videos mention each place, then verify each with Nominatim in the
   destination's country; drop unverified, wrong-country, or implausible matches (e.g. an area
   that geocodes to a single business) and the destination itself.
4. Return up to `MAX_SPOTS` (10) spots, each linking back to its videos.

API:

- `trending_spots(destination, month="", interests="", max_spots=10) -> Discovery`
- `spots_from_links(links, destination="", max_spots=10) -> Discovery` — up to `MAX_LINKS` (10)
  pasted TikTok URLs, each looked up in Google's index to read its caption; links that are not
  TikTok or not yet indexed are reported in `notes`.
- `Discovery` — `destination`, `videos`, `spots`, `unverified`, `center`, `notes`;
  `to_dict()` and `to_brief()` (a markdown summary usable as crew inspiration).
- `Spot` — `name`, `kind`, `why`, `mentions`, `videos`, `lat`, `lon`, `address`, `osm_url`,
  `distance_km` (only when the destination is a city), `verified`.

## Travel lookups — `travel_info.py`

Each returns a plain dict (so the web API and MCP server can pass it straight through) and
raises `LookupError_` with a traveller-friendly message on failure.

- `typical_weather(place, month)` — averages from the most recent complete occurrence of that
  month in Open-Meteo's historical archive: avg high/low, coldest night, hottest day, rainy
  days, total rain (°C / mm). Not a forecast. Cached.
- `prayer_times(place, day="")` — Fajr, Sunrise, Dhuhr, Asr, Maghrib, Isha for `day`
  (YYYY-MM-DD, default today) from the AlAdhan API, which picks the local calculation method;
  includes the Hijri date. Cached.
- `transfer_options(origin, destination)` — straight-line distance plus the top 5 Serper results
  about trains, buses, louages/taxis, and flights, so callers summarise real sourced options.

## Background jobs — `jobs.py`

- `PHASES` — seven `(icon, label)` pairs, one per crew task in run order.
- `PlanJob(origin, cities, travel_dates, interests, inspiration="")` — dataclass with `id`
  (12 hex chars), `status` (`queued | running | done | error`), `completed`, `steps`, `result`,
  `error`. `run()` runs `TripCrew` in the calling thread, counting steps and completed tasks via
  the crew callbacks; `start()` runs it on a daemon thread; `phase` and `to_dict()` expose only
  abstracted progress, never raw reasoning.

## Orchestration — `crew.py` and `__main__.py`

`TripCrew(origin, cities, date_range, interests, inspiration="")` (in `crew.py`) builds the
seven agents and tasks, wires the handoff via task `context`, and runs the crew. The optional
`inspiration` text is passed to the curator task. On Groq it paces steps
(`GROQ_STEP_DELAY_SECONDS`) and retries the whole crew on transient `tool_use_failed` errors
(`CREW_MAX_ATTEMPTS`). `run()` accepts optional `step_callback`/`task_callback` for progress.
`__main__.main()` reconfigures stdout to UTF-8 (Windows-safe), validates the environment,
collects CLI input, and prints the result. See [Architecture](architecture.md) for the wiring
diagram.

## Web app — `web/`

- `web/app.py` — the FastAPI `app` (title "ReelTrip", OpenAPI docs at `/api/docs`). Routes: `/`
  (planner page), `/p/{id}` (share page for a finished plan), `POST /api/discover` (up to
  `MAX_DISCOVER_CITIES` = 3 destinations plus pasted links), `POST /api/plans` (starts a
  `PlanJob`; 422 on bad dates/empty fields, 429 when `VOYAGENT_MAX_ACTIVE_PLANS` are running,
  503 when keys are missing), `GET /api/plans/{id}`, `GET /healthz`, and the MCP server mounted
  at `/mcp` (stateless streamable HTTP with DNS-rebinding protection; the MCP session manager
  runs in the app's lifespan). Finished plans are saved as JSON under
  `VOYAGENT_DATA_DIR/plans/`. `VOYAGENT_SUPPORT_URL` adds an optional support link.
- `web/__main__.py` — `python -m voyagent.web [--host] [--port] [--reload]` (defaults from
  `HOST` / `PORT`, else `127.0.0.1:8000`); console script `voyagent-web`.
- `web/templates/` — Jinja2: `base.html` (layout, Open Graph tags, footer), `index.html`
  (form, TikTok discovery map, phase list, result actions), `plan.html` (share page).
- `web/static/` — `app.js` (vanilla JS: discovery, keep/skip spots, Leaflet map on
  OpenStreetMap tiles, polling, share/download/print; Markdown rendered with marked +
  DOMPurify) and `style.css`.

## MCP server — `mcp_server.py`

An `MCPServer` (MCP Python SDK 2.x) named `voyagent`, with instructions that steer the host
assistant to use the fast grounded lookups and build the itinerary itself. Blocking lookups run
in worker threads.

| Tool | Backed by |
|---|---|
| `trending_spots(destination, month="", interests="")` | `social.trending_spots` |
| `spots_from_tiktok_links(links, destination="")` | `social.spots_from_links` |
| `verify_place(name, near="")` | `places.verify_place` (returns `found: false` when missing) |
| `typical_weather(place, month)` | `travel_info.typical_weather` |
| `prayer_times(place, date="")` | `travel_info.prayer_times` |
| `transfer_options(origin, destination)` | `travel_info.transfer_options` |
| `plan_trip(origin, destinations, travel_dates, interests, inspiration="")` | `PlanJob` / `TripCrew` (slow; reports progress per phase; CrewAI output redirected to stderr) |

`main()` runs stdio by default or streamable HTTP with `--http [--host] [--port]` (defaults
`127.0.0.1:8000`); console script `voyagent-mcp`. The web app imports the same `mcp` object and
mounts it at `/mcp`.
