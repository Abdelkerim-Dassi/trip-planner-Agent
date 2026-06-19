# Trip Planner Agent — Documentation

A multi-agent AI travel planner built on [CrewAI](https://www.crewai.com/). You give it an
origin city, candidate destinations, a date range, and your interests; three specialized
agents collaborate to pick the best city, gather local insights, and produce a complete
day-by-day itinerary with budget and packing notes.

## Documentation index

| Doc | What it covers |
|---|---|
| [Architecture](architecture.md) | How the crew, agents, tasks, and tools fit together; execution flow |
| [Setup](setup.md) | Prerequisites, installation, environment variables |
| [Usage](usage.md) | Running the planner, inputs, and example output |
| [Agents, Tasks & Tools reference](reference.md) | Per-component reference for the `trip_planner` package |
| [Configuration & extension](configuration.md) | Swapping LLMs, adding tools, tuning behavior |
| [Audit & changelog](audit.md) | The audit that produced the current structure and the fixes applied |

## Quick links

- Entry point: [`src/trip_planner/__main__.py`](../src/trip_planner/__main__.py)
- Orchestration: [`src/trip_planner/crew.py`](../src/trip_planner/crew.py)
- Agent definitions: [`src/trip_planner/agents.py`](../src/trip_planner/agents.py)
- Task definitions: [`src/trip_planner/tasks.py`](../src/trip_planner/tasks.py)
- Config: [`src/trip_planner/config.py`](../src/trip_planner/config.py)
- Tools: [`src/trip_planner/tools/`](../src/trip_planner/tools/)

## At a glance

- **Language / tooling:** Python 3.10–3.11, [Poetry](https://python-poetry.org/) (src layout)
- **Framework:** CrewAI (`^0.130.0`) for multi-agent orchestration
- **LLM:** OpenAI `gpt-4o-mini` via `langchain-openai`'s `ChatOpenAI` (configurable)
- **Web search:** Serper.dev Google Search API
- **Run mode:** Interactive CLI (`python -m trip_planner` or `trip-planner`)
