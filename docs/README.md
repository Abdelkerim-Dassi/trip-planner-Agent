# Voyagent — Documentation

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
| [Agents, Tasks & Tools reference](reference.md) | Per-component reference for the `voyagent` package |
| [Configuration & extension](configuration.md) | Swapping LLMs, adding tools, tuning behavior |
| [Audit & changelog](audit.md) | The audit that produced the current structure and the fixes applied |

## Quick links

- Entry point: [`src/voyagent/__main__.py`](../src/voyagent/__main__.py)
- Orchestration: [`src/voyagent/crew.py`](../src/voyagent/crew.py)
- Agent definitions: [`src/voyagent/agents.py`](../src/voyagent/agents.py)
- Task definitions: [`src/voyagent/tasks.py`](../src/voyagent/tasks.py)
- Config: [`src/voyagent/config.py`](../src/voyagent/config.py)
- Tools: [`src/voyagent/tools/`](../src/voyagent/tools/)

## At a glance

- **Language / tooling:** Python 3.10–3.11, [Poetry](https://python-poetry.org/) (src layout)
- **Framework:** CrewAI (`^0.130.0`) for multi-agent orchestration
- **LLM:** OpenAI `gpt-4o-mini` via `langchain-openai`'s `ChatOpenAI` (configurable)
- **Web search:** Serper.dev Google Search API
- **Run mode:** Interactive CLI (`python -m voyagent` or `voyagent`)
