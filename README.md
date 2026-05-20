# Trip Planner Agent

A multi-agent AI travel planner built on [CrewAI](https://www.crewai.com/). Give it an origin city, candidate destinations, a date range, and your interests — three specialized agents collaborate to pick the best city, dig up local insights, and return a complete day-by-day itinerary with budget and packing notes.

## How it works

Three CrewAI agents run sequentially, each with its own role, tools, and reasoning loop:

| Agent | Role | What it does |
|---|---|---|
| **City Selection Expert** | Analyzes travel data across candidate destinations | Weighs weather, season, and pricing to recommend the best city to visit. Uses web search + calculator. Backed by `o1-mini` for reasoning. |
| **Local Expert** | Acts as a knowledgeable resident of the selected city | Gathers attractions, customs, hidden gems, and seasonal events. Uses web search. |
| **Travel Concierge** | Builds the final deliverable | Produces a detailed itinerary with daily schedules, budget breakdown, and a packing list. Uses web search + calculator. |

The agents are coordinated by a `Crew` defined in `main.py`, which kicks off three tasks (`identify_city`, `gather_city_info`, `plan_itinerary`) in turn.

## Tech stack

- **Python 3** with **Poetry** for dependency management
- **CrewAI** — multi-agent orchestration framework
- **LangChain + `langchain-openai`** — `ChatOpenAI` wrapper with `o1-mini`
- **SerperDev / web search** — `tools/search_tools.py`
- **Custom calculator tool** — `tools/calculator_tools.py`
- **python-dotenv** — environment variable management

## Repository structure

```
.
├── main.py                       # Entry point — CLI prompts + Crew orchestration
├── agents.py                     # 3 agent definitions (role, goal, tools, LLM)
├── tasks.py                      # Task definitions (plan_itinerary, identify_city, gather_city_info)
├── tools/
│   ├── search_tools.py           # Internet search tool
│   └── calculator_tools.py       # Calculator tool for budget math
├── .env_example                  # Template for required API keys
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
pip install crewai langchain-openai python-dotenv
```

### 3. Configure API keys

Copy `.env_example` to `.env` and fill in:

```bash
cp .env_example .env
```

```env
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
```

`OPENAI_API_KEY` powers the agents (via `o1-mini`); `SERPER_API_KEY` (or whatever search provider `tools/search_tools.py` uses) powers the web search tool.

### 4. Run

```bash
python main.py
```

You'll be prompted for four inputs:

```
Enter origin: Tunis
Enter destination: Lisbon, Porto, Barcelona
Enter travel time range: 15 June - 22 June
Enter interests: food, architecture, beach
```

The crew runs (with `verbose=True`, so you'll see each agent's reasoning), and the final trip plan prints to the terminal.

## Example output

A typical run produces something like:

- A picked city (with justification: weather, prices, fit to interests)
- A local guide section: top attractions, neighborhoods, local customs, seasonal events
- A 7-day itinerary: daily activities, restaurant suggestions, transit notes
- Budget estimate broken down by category
- A packing list tailored to forecast weather

## Configuration

To change the LLM used by an agent, edit `agents.py` — each agent currently uses `ChatOpenAI(model='o1-mini', temperature=0.2)`. Swap in another OpenAI model or any LangChain-compatible chat model. To extend the toolset, add a new tool in `tools/` and attach it to the relevant agent in `agents.py`.

## License

Personal / educational project.
