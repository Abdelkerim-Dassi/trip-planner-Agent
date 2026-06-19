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

## Agents — `agents.py`

The `TravelAgents` class builds the shared LLM once in `__init__` and exposes three factory
methods, each returning a configured CrewAI `Agent`. All agents set `max_iter=10`,
`allow_delegation=False`, and `verbose=False`, and their goals/backstories stress verified,
local-only information.

### `city_selection_agent()`
- **role:** City Selection Expert
- **goal:** Pick the single best city from the candidate list using only facts found via search
- **tools:** `SearchTools.search_internet`, `CalculatorTool.calculate`

### `local_expert()`
- **role:** Local Expert at this city
- **goal:** Describe the selected city accurately using only verified, local information
- **tools:** `SearchTools.search_internet`

### `travel_concierge()`
- **role:** Amazing Travel Concierge
- **goal:** Turn the city guide into an accurate itinerary, weather, packing list, and budget
- **tools:** `SearchTools.search_internet`, `CalculatorTool.calculate`

## Tasks — `tasks.py`

The `TravelTasks` class exposes three task factories. Each returns a CrewAI `Task` whose
`description` is a templated prompt with an `expected_output`. A shared `_GROUNDING_RULES`
block is injected into every prompt (verify via search; real in-country places only; links
copied verbatim from results only — never guessed; omit unverifiable details; write only for
the traveller). A private `__tip_section()` appends a "$10,000 commission" incentive line.

### `identify_city(agent, origin, cities, travel_dates, interests)`
- **Purpose:** Recommend **one** city chosen only from `cities` (never the origin).
- **expected_output:** The selected city plus a short justification (weather for the dates,
  approximate flight cost, fit to interests).

### `gather_city_info(agent, travel_dates, interests, context=None)`
- **Purpose:** Compile an in-depth guide for the **selected** city (read from `context`, which
  is set to `[identify_city]` by the crew).
- **expected_output:** A guide to the selected city — attractions, neighborhoods, customs, local
  food, and events during the dates, all verified via search.

### `plan_itinerary(agent, travel_dates, interests, context=None)`
- **Purpose:** Expand the guide (from `context=[gather_city_info]`) into a day-by-day itinerary
  covering **exactly** the travel dates.
- **expected_output:** A complete markdown plan that starts directly with the plan: per-day
  schedule for the exact dates, weather in °C, packing list, and a budget table in one
  consistent currency.

> The previous fixed "7-day" wording has been removed; the itinerary length follows the dates.
> The `city` parameter was dropped from `gather_city_info`/`plan_itinerary` in favor of `context`.

## Tools — `tools/`

### `SearchTools.search_internet(query)` — `search_tools.py`
- Decorated with `@tool("Search the internet")`.
- Sends `query` to the Serper.dev Google Search API (`https://google.serper.dev/search`) with a
  15-second timeout.
- Reads the key via `os.environ.get("SERPER_API_KEY")` and returns a friendly message if it is
  missing or the request fails (no uncaught exceptions).
- Returns the top **2** organic results (`TOP_RESULTS_TO_RETURN`), each as Title / Link /
  Snippet, with snippets truncated to `MAX_SNIPPET_CHARS` (150) — kept small to limit token use
  on rate-limited free tiers.

### `CalculatorTool.calculate(operation)` — `calculator_tools.py`
- Decorated with `@tool("Make a calculation")`.
- Evaluates a math expression string (e.g. `'200*7'`) with a **restricted AST evaluator** — only
  numeric literals and arithmetic operators (`+ - * / // % **`, unary `+/-`) are allowed, so
  arbitrary code cannot be executed.
- Handles division-by-zero and invalid/unsupported expressions with friendly messages.

## Orchestration — `crew.py` and `__main__.py`

`TripCrew(origin, cities, date_range, interests)` (in `crew.py`) builds the agents and tasks,
wires the city handoff via task `context`, and runs the crew. On Groq it paces steps
(`GROQ_STEP_DELAY_SECONDS`) and retries the whole crew on transient `tool_use_failed` errors
(`CREW_MAX_ATTEMPTS`). `run()` accepts optional `step_callback`/`task_callback` for UI progress.
`__main__.main()` reconfigures stdout to UTF-8 (Windows-safe), validates the environment,
collects CLI input, and prints the result. See [Architecture](architecture.md) for the wiring
diagram.

## Web UI — `streamlit_app.py`

Wraps `TripCrew` in a form (with a date-range picker), runs it on a worker thread, and shows an
abstracted 3-phase progress bar — never the raw agent reasoning. Copies `st.secrets` into the
environment at startup so the same `config.py` logic works on Streamlit Community Cloud. Styling
uses `st.html` + inline styles plus `.streamlit/config.toml` (Tropical Sunset theme).
