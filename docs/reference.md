# Agents, Tasks & Tools reference

A per-component reference for the `voyagent` package.

## Configuration — `config.py`

The single source of truth for environment and model setup.

- `MODEL_NAME` — chat model name (default `gpt-4o-mini`; override with `VOYAGENT_MODEL`).
- `MODEL_TEMPERATURE` — sampling temperature (default `0.2`; override with `VOYAGENT_TEMPERATURE`).
- `REQUIRED_KEYS` — `("OPENAI_API_KEY", "SERPER_API_KEY")`.
- `validate_env()` — raises `MissingConfigError` listing any missing keys.
- `build_llm()` — returns a `ChatOpenAI` configured with the model + temperature above
  (imports `langchain_openai` lazily).

## Agents — `agents.py`

The `TravelAgents` class builds the shared LLM once in `__init__` and exposes three factory
methods, each returning a configured CrewAI `Agent`.

### `city_selection_agent()`
- **role:** City Selection Expert
- **goal:** Select the best city based on weather, season, and prices
- **tools:** `SearchTools.search_internet`, `CalculatorTool.calculate`
- **llm:** shared `gpt-4o-mini`

### `local_expert()`
- **role:** Local Expert at this city
- **goal:** Provide the BEST insights about the selected city
- **tools:** `SearchTools.search_internet`
- **llm:** shared `gpt-4o-mini`

### `travel_concierge()`
- **role:** Amazing Travel Concierge
- **goal:** Create the most amazing travel itineraries with budget and packing suggestions
- **tools:** `SearchTools.search_internet`, `CalculatorTool.calculate`
- **llm:** shared `gpt-4o-mini`

## Tasks — `tasks.py`

The `TravelTasks` class exposes three task factories. Each returns a CrewAI `Task` whose
`description` is a templated prompt and which carries an `expected_output`. A private
`__tip_section()` appends a "$10,000 commission" incentive line to every prompt.

### `identify_city(agent, origin, cities, travel_dates, interests)`
- **Purpose:** Analyze candidate cities and recommend the most suitable one.
- **expected_output:** "Detailed report on the chosen city including flight costs, weather forecast, and attractions."

### `gather_city_info(agent, city, travel_dates, interests)`
- **Purpose:** Compile an in-depth guide for the selected city.
- **expected_output:** "A detailed city guide including attractions, local customs, events, and daily activities."

### `plan_itinerary(agent, city, travel_dates, interests)`
- **Purpose:** Expand the city guide into a full 7-day itinerary.
- **expected_output:** A complete expanded travel plan formatted as markdown.

## Tools — `tools/`

### `SearchTools.search_internet(query)` — `search_tools.py`
- Decorated with `@tool("Search the internet")`.
- Sends `query` to the Serper.dev Google Search API (`https://google.serper.dev/search`)
  with a 15-second timeout.
- Reads the key via `os.environ.get("SERPER_API_KEY")` and returns a friendly message if it
  is missing or the request fails (no uncaught exceptions).
- Returns the top 5 organic results, each formatted as Title / Link / Snippet.

### `CalculatorTool.calculate(operation)` — `calculator_tools.py`
- Decorated with `@tool("Make a calculation")`.
- Evaluates a math expression string (e.g. `'200*7'`) with a **restricted AST evaluator** —
  only numeric literals and arithmetic operators (`+ - * / // % **`, unary `+/-`) are allowed,
  so arbitrary code cannot be executed.
- Handles division-by-zero and invalid/unsupported expressions with friendly messages.

## Orchestration — `crew.py` and `__main__.py`

`TripCrew(origin, cities, date_range, interests)` (in `crew.py`) builds the agents and tasks,
wires each agent to its matching task, and runs `Crew.kickoff()`. `__main__.main()` validates
the environment, collects CLI input, and prints the result. See [Architecture](architecture.md)
for the wiring diagram.
