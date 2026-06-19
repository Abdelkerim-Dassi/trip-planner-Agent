# Architecture

Voyagent is a **sequential multi-agent system** orchestrated by CrewAI. Three agents, each
with a distinct role and toolset, run as a `Crew` to transform raw trip inputs into a finished
travel plan.

## Package layout

```
src/voyagent/
  __main__.py    CLI entry point. Validates env, collects input, runs the crew. (python -m voyagent)
  crew.py        TripCrew — wires agents to tasks (with context handoff), throttles/retries on Groq, runs kickoff.
  agents.py      TravelAgents — factory class returning three configured CrewAI Agents.
  tasks.py       TravelTasks — factory class returning three CrewAI Tasks (grounded prompts).
  config.py      Env loading, provider/model selection, key validation (validate_env), shared LLM (build_llm).
  tools/
    search_tools.py      SearchTools.search_internet — Serper.dev Google search.
    calculator_tools.py  CalculatorTool.calculate — safe AST evaluator for budget math.
streamlit_app.py         Streamlit web UI wrapping the same TripCrew.
.streamlit/config.toml    Streamlit theme (Tropical Sunset palette).
```

## The LLM (provider-switchable)

All three agents share a single model instance built once by `config.build_llm()`:

- `VOYAGENT_PROVIDER=openai` (default) → a `langchain_openai.ChatOpenAI` (`gpt-4o-mini`).
- `VOYAGENT_PROVIDER=groq` → a `crewai.LLM` using a LiteLLM `groq/<model>` (default
  `llama-3.3-70b-versatile`), with `num_retries` so it waits out Groq's rate-limit 429s.

Change the model in one place — `config.py`, or the `VOYAGENT_MODEL` / `VOYAGENT_TEMPERATURE`
env vars.

## The three agents

| Agent (method in `agents.py`) | Role | Tools |
|---|---|---|
| `city_selection_agent` | **City Selection Expert** — weighs weather, season, and prices to pick the best city from the candidate list | `search_internet`, `calculate` |
| `local_expert` | **Local Expert** — surfaces real attractions, customs, and hidden gems in the selected city | `search_internet` |
| `travel_concierge` | **Travel Concierge** — builds the final itinerary, budget, and packing list | `search_internet`, `calculate` |

Each agent sets `max_iter` (10) to cap its tool loop, `allow_delegation=False`, and
`verbose=False`. Goals and backstories stress using only verified, local information.

## The three tasks

Defined in `tasks.py`, each task is a templated prompt with `expected_output`. A shared
`_GROUNDING_RULES` block is injected into every prompt: verify via search, real in-country
places only, no invented links (URLs copied verbatim from results only), omit what can't be
verified, write only for the traveller.

- `identify_city(agent, origin, cities, travel_dates, interests)` — recommend **one** city from
  the candidates (never the origin), justified by weather/events/cost.
- `gather_city_info(agent, travel_dates, interests, context=[identify_city])` — compile a guide
  for the **selected** city (read from context).
- `plan_itinerary(agent, travel_dates, interests, context=[gather_city_info])` — expand into a
  day-by-day itinerary covering **exactly** the travel dates, with weather in °C, a packing
  list, and a budget table in one consistent currency.

Every task prompt ends with a `__tip_section()` line offering a "$10,000 commission" — a
prompt-engineering nudge to encourage thorough output.

## Execution flow

```
User input (origin, cities, date range, interests)   ──CLI or Streamlit form
        │
        ▼
   validate_env()  ── fails fast if the provider key or SERPER_API_KEY is missing
        │
        ▼
   TripCrew.run()
        │  builds agents + tasks, wires context handoff; on Groq, installs a step throttle
        │  and retries the crew on transient tool-call errors
        ▼
   Crew.kickoff()  ── runs tasks sequentially (verbose=False) ──▶ final trip plan (markdown)
```

The `Crew` is constructed in `crew.py` with each agent owning the task that matches its role:

```python
identify_city    = tasks.identify_city(city_selector, origin, cities, date_range, interests)
gather_city_info = tasks.gather_city_info(local_expert, date_range, interests, context=[identify_city])
plan_itinerary   = tasks.plan_itinerary(concierge, date_range, interests, context=[gather_city_info])

crew = Crew(
    agents=[city_selector, local_expert, concierge],
    tasks=[identify_city, gather_city_info, plan_itinerary],
    verbose=False,
    step_callback=step_callback,   # optional; UI progress + Groq throttle
    task_callback=task_callback,   # optional; fires when each task finishes
)
```

## Data flow between tasks

The selected city flows forward through **explicit task context** (`context=[...]`), not by
re-passing the candidate list: `gather_city_info` reads `identify_city`'s output, and
`plan_itinerary` reads the guide. This is what keeps the downstream agents planning for the
*chosen* city rather than the whole candidate list or the origin. Agents reach out to the web
(Serper) and the calculator on demand within their reasoning loops.

## Resilience on Groq's free tier

`crew.py` adds two safeguards used only when `VOYAGENT_PROVIDER=groq`:

- **Throttling:** a `step_callback` wrapper sleeps `GROQ_STEP_DELAY_SECONDS` (default 10s)
  between agent steps to stay under Groq's tokens-per-minute cap.
- **Retry:** if Groq rejects a malformed tool call (`tool_use_failed`), `run()` rebuilds and
  re-runs the crew up to `CREW_MAX_ATTEMPTS` (default 3) times.
