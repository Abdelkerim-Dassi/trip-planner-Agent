# Voyagent — Documentation

A multi-agent AI travel planner built on [CrewAI](https://www.crewai.com/). You give it an
origin city, candidate destinations, a date range, and your interests; seven specialized
agents run in sequence to pick the best city, research it, and produce a verified
day-by-day itinerary with logistics, budget and packing notes. It can also turn what
travellers share on TikTok into verified, mapped trip ideas. It runs for free on Groq or on
OpenAI, via a CLI, a FastAPI web app, or as an MCP server inside Claude and ChatGPT.

## Documentation index

| Doc | What it covers |
|---|---|
| [Architecture](architecture.md) | How the crew, agents, tasks, tools, web app and MCP server fit together; execution and data flow |
| [Setup](setup.md) | Prerequisites, installation, provider/environment variables |
| [Usage](usage.md) | Running the CLI, the web app and the MCP server; inputs and example output |
| [Agents, Tasks & Tools reference](reference.md) | Per-component reference for the `voyagent` package |
| [Configuration & extension](configuration.md) | Switching providers/LLMs, adding tools, tuning behavior, env vars |
| [Audit & changelog](audit.md) | The original audit plus the changelog of later changes |

## Quick links

- CLI entry point: [`src/voyagent/__main__.py`](../src/voyagent/__main__.py)
- Orchestration: [`src/voyagent/crew.py`](../src/voyagent/crew.py)
- Agent definitions: [`src/voyagent/agents.py`](../src/voyagent/agents.py)
- Task definitions: [`src/voyagent/tasks.py`](../src/voyagent/tasks.py)
- Config: [`src/voyagent/config.py`](../src/voyagent/config.py)
- Tools: [`src/voyagent/tools/`](../src/voyagent/tools/)
- TikTok discovery: [`src/voyagent/social.py`](../src/voyagent/social.py)
- Web app: [`src/voyagent/web/`](../src/voyagent/web/)
- MCP server: [`src/voyagent/mcp_server.py`](../src/voyagent/mcp_server.py)
- Container: [`Dockerfile`](../Dockerfile)

## At a glance

- **Language / tooling:** Python 3.10–3.11, `pip` or [Poetry](https://python-poetry.org/) (src layout)
- **Framework:** CrewAI (`crewai[litellm]`, `^0.130.0`) for multi-agent orchestration
- **LLM:** provider-switchable — OpenAI `gpt-4o-mini` (default) or Groq `llama-3.3-70b-versatile`
  (free), selected with `VOYAGENT_PROVIDER`
- **Web search:** Serper.dev Google Search API (shared, cached client)
- **Open data:** OpenStreetMap Nominatim (place verification), Open-Meteo (typical weather),
  AlAdhan (prayer times)
- **Run modes:** interactive CLI (`python -m voyagent` / `voyagent`), FastAPI web app
  (`python -m voyagent.web`), MCP server (`python -m voyagent.mcp_server`, also served by the
  web app at `/mcp`)
- **Hosting:** `Dockerfile` for Render's free plan or any container host
