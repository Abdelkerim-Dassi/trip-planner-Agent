# Architecture

The Trip Planner Agent is a **sequential multi-agent system** orchestrated by CrewAI. Three
agents, each with a distinct role and toolset, run as a `Crew` to transform raw trip inputs
into a finished travel plan.

## Package layout

```
src/trip_planner/
  __main__.py    CLI entry point. Validates env, collects input, runs the crew. (python -m trip_planner)
  crew.py        TripCrew — wires agents to tasks and runs crew.kickoff().
  agents.py      TravelAgents — factory class returning three configured CrewAI Agents.
  tasks.py       TravelTasks — factory class returning three CrewAI Tasks (prompts).
  config.py      Env loading, key validation (validate_env), and the shared LLM (build_llm).
  tools/
    search_tools.py      SearchTools.search_internet — Serper.dev Google search.
    calculator_tools.py  CalculatorTool.calculate — safe AST evaluator for budget math.
```

## The three agents

| Agent (method in `agents.py`) | Role | Tools | LLM |
|---|---|---|---|
| `city_selection_agent` | **City Selection Expert** — weighs weather, season, and prices to pick the best city | `search_internet`, `calculate` | shared `gpt-4o-mini` |
| `local_expert` | **Local Expert** — surfaces attractions, customs, and hidden gems | `search_internet` | shared `gpt-4o-mini` |
| `travel_concierge` | **Travel Concierge** — builds the final itinerary, budget, and packing list | `search_internet`, `calculate` | shared `gpt-4o-mini` |

All three agents share a single model instance built once by `config.build_llm()`. Change the
model in one place (`config.py`, or the `TRIP_PLANNER_MODEL` env var).

## The three tasks

Defined in `tasks.py`, each task is a richly templated prompt with `expected_output`:

- `identify_city` — analyze candidate cities and recommend one (weather, events, cost).
- `gather_city_info` — compile an in-depth guide for the chosen city.
- `plan_itinerary` — expand the guide into a 7-day itinerary with budget and packing list.

Every task prompt ends with a `__tip_section()` line offering a "$10,000 commission" — a
prompt-engineering nudge to encourage thorough output.

## Execution flow

```
User input (origin, cities, date range, interests)
        │
        ▼
   __main__.main()  ── validate_env() fails fast if keys are missing
        │
        ▼
   TripCrew.run()
        │  builds agents + tasks, wired by role
        ▼
   Crew.kickoff()   ── runs tasks sequentially, verbose=True ──▶ final trip plan (markdown)
```

The `Crew` is constructed in `crew.py` with each agent owning the task that matches its role,
in logical order:

```python
crew = Crew(
    agents=[city_selector, local_expert, concierge],
    tasks=[identify_city, gather_city_info, plan_itinerary],
    verbose=True,
)
```

## Data flow between tasks

CrewAI passes context between tasks during a sequential run, so the city chosen in
`identify_city` informs `gather_city_info`, which in turn feeds `plan_itinerary`. Agents reach
out to the web (Serper) and the calculator on demand within their reasoning loops.
