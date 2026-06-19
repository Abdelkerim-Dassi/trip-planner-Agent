# Configuration & extension

## Changing the LLM

The model is configured in **one place** — `src/trip_planner/config.py`:

```python
MODEL_NAME = os.environ.get("TRIP_PLANNER_MODEL", "gpt-4o-mini")
MODEL_TEMPERATURE = float(os.environ.get("TRIP_PLANNER_TEMPERATURE", "0.2"))
```

`config.build_llm()` returns a single `ChatOpenAI` instance that all three agents share, so
you never edit per-agent model settings.

To change the model, either:

- Set an environment variable (no code change): `TRIP_PLANNER_MODEL=gpt-4o`, or
- Edit `MODEL_NAME` in `config.py`.

To use a non-OpenAI, LangChain-compatible chat model, change the implementation of
`build_llm()` to construct that model instead.

## Adding a tool

1. Create a function in `src/trip_planner/tools/` decorated with CrewAI's `@tool("name")`:

   ```python
   from crewai.tools import tool

   class WeatherTools:
       @tool("Get weather forecast")
       def forecast(location: str) -> str:
           """Return a weather forecast for the given location."""
           ...
   ```

2. Export it from `tools/__init__.py` and attach it to the relevant agent in `agents.py`:

   ```python
   from trip_planner.tools import SearchTools, WeatherTools

   tools=[SearchTools.search_internet, WeatherTools.forecast]
   ```

The dependency list (`pyproject.toml`) already includes `pyowm`, suggesting OpenWeatherMap
integration was intended — a weather tool is a natural extension.

## Tuning prompts / behavior

- **Trip length:** the itinerary is hard-coded to 7 days in `tasks.plan_itinerary`. Edit the
  prompt text to change it.
- **Search depth:** `SearchTools` returns the top 5 results (`TOP_RESULTS_TO_RETURN`). Raise it
  for more context per search. Adjust `REQUEST_TIMEOUT_SECONDS` for the HTTP timeout.
- **Incentive line:** `TravelTasks.__tip_section()` injects the "$10,000 commission" nudge into
  every task prompt; edit or remove it there.
- **Verbosity:** `Crew(..., verbose=True)` in `crew.py` controls the live reasoning logs.

## Environment variables

See [Setup](setup.md). The code reads:

| Variable | Used by | Required |
|---|---|---|
| `OPENAI_API_KEY` | agents (`ChatOpenAI`) | Yes |
| `SERPER_API_KEY` | `SearchTools.search_internet` | Yes |
| `OPENAI_ORGANIZATION_ID` | OpenAI client (optional) | No |
| `TRIP_PLANNER_MODEL` | model selection | No (default `gpt-4o-mini`) |
| `TRIP_PLANNER_TEMPERATURE` | sampling temperature | No (default `0.2`) |
