# Voyagent

A multi-agent AI travel planner built on [CrewAI](https://www.crewai.com/). Give it an origin city, candidate destinations, a date range, and your interests — three specialized agents collaborate to pick the best city, dig up local insights, and return a complete day-by-day itinerary with budget and packing notes.

## How it works

Three CrewAI agents run sequentially, each with its own role, tools, and reasoning loop:

| Agent | Role | What it does |
|---|---|---|
| **City Selection Expert** | Analyzes travel data across candidate destinations | Weighs weather, season, and pricing to recommend the best city to visit. Uses web search + calculator. |
| **Local Expert** | Acts as a knowledgeable resident of the selected city | Gathers attractions, customs, hidden gems, and seasonal events. Uses web search. |
| **Travel Concierge** | Builds the final deliverable | Produces a detailed itinerary with daily schedules, budget breakdown, and a packing list. Uses web search + calculator. |

All three agents share a single `gpt-4o-mini` model configured in `src/voyagent/config.py`. They are coordinated by a `Crew` defined in `src/voyagent/crew.py`, which runs three tasks in logical order: `identify_city` → `gather_city_info` → `plan_itinerary`.

## Tech stack

- **Python 3** with **Poetry** for dependency management
- **CrewAI** — multi-agent orchestration framework
- **LangChain + `langchain-openai`** — `ChatOpenAI` wrapper with `gpt-4o-mini`
- **SerperDev / web search** — `tools/search_tools.py`
- **Custom calculator tool** — `tools/calculator_tools.py` (safe AST evaluator)
- **python-dotenv** — environment variable management

## Repository structure

```
.
├── src/
│   └── voyagent/
│       ├── __main__.py           # CLI entry point (python -m voyagent)
│       ├── crew.py               # TripCrew — Crew orchestration
│       ├── agents.py             # 3 agent definitions (role, goal, tools, LLM)
│       ├── tasks.py              # Task definitions (identify_city, gather_city_info, plan_itinerary)
│       ├── config.py             # Env loading, key validation, model config
│       └── tools/
│           ├── search_tools.py   # Internet search tool (Serper.dev)
│           └── calculator_tools.py  # Calculator tool for budget math
├── docs/                         # Project documentation
├── .env.example                  # Template for required API keys
├── requirements.txt              # pip alternative to Poetry
├── pyproject.toml                # Poetry project + dependencies
└── poetry.lock
```

## Getting started

### 1. Clone

```bash
git clone https://github.com/Abdelkerim-Dassi/trip-planner-Agent.git
cd trip-planner-Agent
```

### 2. Install dependencies (Poetry recommended)

```bash
poetry install
poetry shell
```

Or with pip:

```bash
pip install -r requirements.txt
```

### 3. Configure API keys

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
```

`OPENAI_API_KEY` powers the agents (via `gpt-4o-mini`); `SERPER_API_KEY` powers the web search tool (Serper.dev). The app validates these at startup and fails fast with a clear message if either is missing.

### 4. Run

```bash
python -m voyagent
# or, after `poetry install`:
voyagent
```

You'll be prompted for four inputs:

```
Enter origin: Tunis
Enter destination: Lisbon, Porto, Barcelona
Enter travel time range: 15 June - 22 June
Enter interests: food, architecture, beach
```

The crew runs (with `verbose=True`, so you'll see each agent's reasoning), and the final trip plan prints to the terminal.

### Web UI

A Streamlit web interface wraps the same crew. After installing dependencies (`pip install -r requirements.txt`, which includes Streamlit) and configuring your `.env` with `OPENAI_API_KEY` and `SERPER_API_KEY`:

```bash
streamlit run streamlit_app.py
```

Fill in origin, candidate destinations, travel dates, and interests, then click **Plan my trip**. Live agent progress streams as the crew works (~1-3 minutes), then the final markdown plan renders with a button to download it as `trip-plan.md`.

Poetry users can add the dependency with `poetry add streamlit`.

## Example output

A typical run produces something like:

- A picked city (with justification: weather, prices, fit to interests)
- A local guide section: top attractions, neighborhoods, local customs, seasonal events
- A 7-day itinerary: daily activities, restaurant suggestions, transit notes
- Budget estimate broken down by category
- A packing list tailored to forecast weather

## Configuration

The model is configured in one place — `src/voyagent/config.py` (`MODEL_NAME`, defaulting to `gpt-4o-mini`). You can override it without editing code via the `VOYAGENT_MODEL` and `VOYAGENT_TEMPERATURE` environment variables. To extend the toolset, add a new tool in `src/voyagent/tools/` and attach it to the relevant agent in `agents.py`. See [docs/configuration.md](docs/configuration.md) for details.

## License

Personal / educational project.
