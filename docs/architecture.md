# Architecture

ReelTrip is a **sequential multi-agent system** orchestrated by CrewAI. Seven agents, each
with a distinct role and toolset, run as a `Crew` to transform raw trip inputs into a finished
travel plan. Around the crew sit a TikTok discovery pipeline, a few grounded lookups (place
verification, typical weather, prayer times, transfers), a FastAPI web app and an MCP server.

## Package layout

```
src/voyagent/
  __main__.py    CLI entry point. Validates env, collects input, runs the crew. (python -m voyagent)
  crew.py        TripCrew — wires the 7 agents to their tasks (context handoff), throttles/retries on Groq, runs kickoff.
  agents.py      TravelAgents — factory class returning the seven configured CrewAI Agents.
  tasks.py       TravelTasks — factory class returning the seven CrewAI Tasks (grounded prompts).
  config.py      Env loading, provider/model selection, key validation (validate_env), shared LLM (build_llm), litellm_model().
  jobs.py        PlanJob — background crew run with abstracted progress (PHASES); used by the web app and MCP server.
  serper.py      Shared Serper.dev search client (per-query cache, SearchError).
  places.py      OpenStreetMap Nominatim verification (~1 req/s throttle, cached) and great-circle distances.
  social.py      TikTok discovery: Serper search -> LLM place extraction -> Nominatim verification -> ranked spots.
  travel_info.py typical_weather (Open-Meteo archive), prayer_times (AlAdhan), transfer_options (Serper).
  mcp_server.py  ReelTrip MCP server (MCP SDK 2.x MCPServer, 7 tools; stdio or --http).
  tools/
    search_tools.py      SearchTools.search_internet — CrewAI tool over serper.py.
    calculator_tools.py  CalculatorTool.calculate — safe AST evaluator for budget math.
  web/
    app.py       FastAPI app: pages, JSON API, /healthz, MCP mounted at /mcp.
    __main__.py  python -m voyagent.web — runs the app with uvicorn.
    templates/   Jinja2 pages: base.html, index.html (planner), plan.html (share page).
    static/      app.js (vanilla JS + Leaflet map), style.css.
Dockerfile       Container for Render's free plan or any container host.
```

## The LLM (provider-switchable)

All seven agents share a single model instance built once by `config.build_llm()`:

- `VOYAGENT_PROVIDER=openai` (default) → a `langchain_openai.ChatOpenAI` (`gpt-4o-mini`).
- `VOYAGENT_PROVIDER=groq` → a `crewai.LLM` using a LiteLLM `groq/<model>` (default
  `openai/gpt-oss-120b`), with `num_retries` so it waits out Groq's rate-limit 429s.

One-off completions outside the crew (TikTok place extraction in `social.py`) call LiteLLM
directly with `config.litellm_model()`, which returns the same configured model as a LiteLLM
id (`groq/<model>` on Groq, the bare model name otherwise).

Change the model in one place — `config.py`, or the `VOYAGENT_MODEL` / `VOYAGENT_TEMPERATURE`
env vars.

## The seven agents

| # | Agent (method in `agents.py`) | Role | Tools |
|---|---|---|---|
| 1 | `city_selection_agent` | **City Selection Expert** — weighs weather, events, and prices to pick the best city from the candidate list | `search_internet`, `calculate` |
| 2 | `local_expert` | **Local Expert** — real attractions, neighbourhoods, customs, and food in the selected city | `search_internet` |
| 3 | `experience_curator` | **Experience Curator** — signature experiences and hidden gems; weighs the traveller's TikTok inspiration | `search_internet` |
| 4 | `travel_concierge` | **Travel Concierge** — drafts the day-by-day itinerary, weather, packing list, and budget | `search_internet`, `calculate` |
| 5 | `logistics_planner` | **Logistics Planner** — getting around, transfers, transit passes, book-ahead flags | `search_internet`, `calculate` |
| 6 | `itinerary_critic` | **Itinerary Critic** — fixes reality, geographic flow, pacing, day count, consistency | `search_internet`, `calculate` |
| 7 | `final_editor` | **Final Editor** — polishes the verified plan into one document; adds no new facts | none |

Each agent sets `max_iter` (10; the tool-less Final Editor uses 3) to cap its loop,
`allow_delegation=False`, and `verbose=False`. Goals and backstories stress using only
verified, local information.

## The seven tasks

Defined in `tasks.py`, each task is a templated prompt with `expected_output`. A shared
`_GROUNDING_RULES` block is injected into the six research/planning prompts: verify via search,
real in-country places only, no invented links (URLs copied verbatim from results only), omit
what can't be verified, write only for the traveller. The final `polish_plan` task uses
`_EDITING_RULES` instead: its agent has no search tool and may only reorganise and rephrase
what is already in the plan.

- `identify_city(agent, origin, cities, travel_dates, interests)` — recommend **one** city from
  the candidates (never the origin), justified by weather/events/cost.
- `gather_city_info(agent, travel_dates, interests, context=[identify_city])` — compile a guide
  for the **selected** city (read from context).
- `curate_experiences(agent, travel_dates, interests, context=[gather_city_info], inspiration)` —
  5–8 signature experiences and hidden gems. If `inspiration` is non-empty,
  `_inspiration_section()` adds the traveller's own places (e.g. the TikTok spots they kept,
  already confirmed on OpenStreetMap) and asks for an honest reality check on each (travel
  time from the city, fit for the season, best time to avoid crowds), plus a one-line reason
  for any it skips.
- `plan_itinerary(agent, travel_dates, interests, context=[gather_city_info, curate_experiences])` —
  day-by-day itinerary covering **exactly** the travel dates, with weather in °C, a packing
  list, and a budget table in one consistent currency.
- `add_logistics(agent, travel_dates, context=[plan_itinerary])` — returns the same plan with a
  Getting Around section, transport notes between stops, pass advice, and book-ahead flags.
- `critique_itinerary(agent, travel_dates, context=[add_logistics], calendar_facts=...)` —
  returns the complete corrected plan (reality, exact day count, currency/budget), restructured
  to follow the `_PACING_RULES` a professional tour planner uses: one area per half-day, buffer
  time, weekly closing days, Ramadan adjustments, and an indoor Plan B on outdoor-heavy days.
  `calendar_facts` comes from `travel_info.calendar_facts` (the weekday of every trip day and
  whether the dates overlap Ramadan), computed in code because models get weekdays wrong.
- `polish_plan(agent, context=[critique_itinerary])` — the final, polished markdown document.

Every task prompt ends with a `__tip_section()` line offering a "$10,000 commission" — a
prompt-engineering nudge to encourage thorough output.

## Execution flow

```
User input (origin, cities, dates, interests)
  ── CLI prompts, web form (+ optional TikTok spots), or MCP plan_trip
        │
        │  web only, optional: POST /api/discover
        │    social.trending_spots / spots_from_links
        │    Serper "site:tiktok.com" → LLM extracts places → Nominatim verifies (destination's
        │    country) → ranked spots on a Leaflet map; the ones the user keeps become `inspiration`
        ▼
   validate_env()  ── fails fast if the provider key or SERPER_API_KEY is missing
        │
        ▼
   PlanJob (web / MCP: background thread, PHASES progress)   or   TripCrew directly (CLI)
        │
        ▼
   TripCrew(origin, cities, date_range, interests, inspiration).run()
        │  builds agents + tasks, wires context handoff; on Groq, installs a step throttle
        │  and retries the crew on transient tool-call errors
        ▼
   Crew.kickoff()  ── 7 tasks sequentially (verbose=False) ──▶ final trip plan (markdown)
        │
        ▼
   CLI prints it · web app saves it to VOYAGENT_DATA_DIR/plans/<id>.json (share page /p/<id>)
   · MCP plan_trip returns it
```

The `Crew` is constructed in `crew.py` with each agent owning the task that matches its role:

```python
identify_city      = tasks.identify_city(city_selector, origin, cities, date_range, interests)
gather_city_info   = tasks.gather_city_info(local_expert, date_range, interests, context=[identify_city])
curate_experiences = tasks.curate_experiences(curator, date_range, interests,
                                              context=[gather_city_info], inspiration=inspiration)
plan_itinerary     = tasks.plan_itinerary(concierge, date_range, interests,
                                          context=[gather_city_info, curate_experiences])
add_logistics      = tasks.add_logistics(logistics, date_range, context=[plan_itinerary])
critique_itinerary = tasks.critique_itinerary(critic, date_range, context=[add_logistics],
                                              calendar_facts=calendar_facts(date_range))
polish_plan        = tasks.polish_plan(editor, context=[critique_itinerary])

crew = Crew(
    agents=[city_selector, local_expert, curator, concierge, logistics, critic, editor],
    tasks=[identify_city, gather_city_info, curate_experiences, plan_itinerary,
           add_logistics, critique_itinerary, polish_plan],
    verbose=False,
    step_callback=step_callback,   # optional; progress + Groq throttle
    task_callback=task_callback,   # optional; fires when each task finishes
)
```

## Data flow between tasks

The selected city flows forward through **explicit task context** (`context=[...]`), not by
re-passing the candidate list: `gather_city_info` reads `identify_city`'s output, the curator
reads the guide, and the concierge reads both the guide and the curated experiences. From
there the plan is progressively refined — logistics, critique, polish — and each of those
steps returns the **complete** plan so the next one can refine it whole. This is what keeps
the downstream agents planning for the *chosen* city rather than the whole candidate list or
the origin. Agents reach out to the web (Serper) and the calculator on demand within their
reasoning loops.

## Web app and MCP server

`web/app.py` is a single FastAPI process that serves:

| Route | Purpose |
|---|---|
| `GET /` | The planner page (form, TikTok discovery map, progress, result) |
| `GET /p/{id}` | Server-rendered share page for a finished plan (previews well on social media) |
| `POST /api/discover` | TikTok-inspired, OpenStreetMap-verified spots for up to 3 destinations and/or pasted links |
| `POST /api/plans` | Start a crew run as a background `PlanJob` (202); at most `VOYAGENT_MAX_ACTIVE_PLANS` at once, else 429 |
| `GET /api/plans/{id}` | Poll a plan's status, phase, and result |
| `GET /healthz` | Health check |
| `GET /api/docs` | OpenAPI docs for the JSON API |
| `/mcp` | The ReelTrip MCP server (streamable HTTP, stateless) |

Jobs report only abstracted progress (one of seven `PHASES`, one per task), never the agents'
raw reasoning. Finished plans are written to `VOYAGENT_DATA_DIR/plans/<id>.json` so share
links outlive the in-memory job. The front end is plain HTML/CSS/JS (no build step) with
Leaflet on OpenStreetMap tiles and Markdown rendered client-side with marked + DOMPurify.

`mcp_server.py` defines an `MCPServer` with seven tools: `trending_spots`,
`spots_from_tiktok_links`, `verify_place`, `typical_weather`, `prayer_times`,
`transfer_options`, and `plan_trip` (the full crew, run through `PlanJob` with progress
reports). It runs over stdio (e.g. Claude Desktop) or streamable HTTP (`--http`); the web app
mounts the same server at `/mcp` with DNS-rebinding protection (allowed hosts: localhost,
`RENDER_EXTERNAL_HOSTNAME`, `SPACE_HOST`, and `VOYAGENT_PUBLIC_HOSTS`).

## Resilience on Groq's free tier

`crew.py` adds two safeguards used only when `VOYAGENT_PROVIDER=groq`:

- **Throttling:** a `step_callback` wrapper sleeps `GROQ_STEP_DELAY_SECONDS` (default 10s)
  between agent steps to stay under Groq's tokens-per-minute cap.
- **Retry:** if Groq rejects a malformed tool call (`tool_use_failed`), `run()` rebuilds and
  re-runs the crew up to `CREW_MAX_ATTEMPTS` (default 3) times.
