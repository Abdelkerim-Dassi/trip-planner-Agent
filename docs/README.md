# Voyagent — Documentation

A multi-agent AI travel planner built on [CrewAI](https://www.crewai.com/). You give it an
origin city, candidate destinations, a date range, and your interests; three specialized
agents collaborate to pick the best city, gather local insights, and produce a complete
day-by-day itinerary with budget and packing notes. It runs for free on Groq or on OpenAI,
via a CLI or a Streamlit web app.

## Documentation index

| Doc | What it covers |
|---|---|
| [Architecture](architecture.md) | How the crew, agents, tasks, and tools fit together; execution and data flow |
| [Setup](setup.md) | Prerequisites, installation, provider/environment variables |
| [Usage](usage.md) | Running the CLI and web app, inputs, and example output |
| [Agents, Tasks & Tools reference](reference.md) | Per-component reference for the `voyagent` package |
| [Configuration & extension](configuration.md) | Switching providers/LLMs, adding tools, tuning behavior |
| [Audit & changelog](audit.md) | The original audit plus the changelog of later changes |

## Quick links

- Entry point: [`src/voyagent/__main__.py`](../src/voyagent/__main__.py)
- Orchestration: [`src/voyagent/crew.py`](../src/voyagent/crew.py)
- Agent definitions: [`src/voyagent/agents.py`](../src/voyagent/agents.py)
- Task definitions: [`src/voyagent/tasks.py`](../src/voyagent/tasks.py)
- Config: [`src/voyagent/config.py`](../src/voyagent/config.py)
- Tools: [`src/voyagent/tools/`](../src/voyagent/tools/)
- Web UI: [`streamlit_app.py`](../streamlit_app.py)

## At a glance

- **Language / tooling:** Python 3.10–3.11, [Poetry](https://python-poetry.org/) (src layout)
- **Framework:** CrewAI (`crewai[litellm]`, `^0.130.0`) for multi-agent orchestration
- **LLM:** provider-switchable — OpenAI `gpt-4o-mini` (default) or Groq `llama-3.3-70b-versatile`
  (free), selected with `VOYAGENT_PROVIDER`
- **Web search:** Serper.dev Google Search API
- **Run modes:** interactive CLI (`python -m voyagent` / `voyagent`) or Streamlit web app
  (`streamlit run streamlit_app.py`, deployable to Streamlit Community Cloud)
