# Voyagent

A multi-agent AI travel planner built on [CrewAI](https://www.crewai.com/). Give it an origin city, candidate destinations, a date range, and your interests — three specialized agents collaborate to pick the best city, dig up local insights, and return a complete day-by-day itinerary with budget and packing notes. It runs **for free on Groq's API** (or on OpenAI), via a CLI or a polished Streamlit web app.

## How it works

Three CrewAI agents run sequentially, each with its own role, tools, and reasoning loop. The city chosen in step 1 is passed forward as task **context**, so the downstream agents research and plan for the *selected* city:

| Agent | Role | What it does |
|---|---|---|
| **City Selection Expert** | Analyzes travel data across candidate destinations | Weighs weather, season, and pricing to recommend the best city — chosen **only** from the candidate list. Uses web search + calculator. |
| **Local Expert** | Acts as a knowledgeable resident of the selected city | Gathers attractions, customs, hidden gems, and seasonal events, verified via search. Uses web search. |
| **Travel Concierge** | Builds the final deliverable | Produces a day-by-day itinerary (matching your exact dates), budget breakdown, and packing list. Uses web search + calculator. |

The agents are told to **ground every claim in the search tool** — only real, in-country places; no invented names; links only when copied verbatim from a result; weather in °C; consistent currency. They're coordinated by a `Crew` in `src/voyagent/crew.py` that runs three tasks in order: `identify_city` → `gather_city_info` → `plan_itinerary`.

All three agents share a single model from `src/voyagent/config.py`. The LLM is **provider-switchable**: OpenAI `gpt-4o-mini` by default, or Groq's free `llama-3.3-70b-versatile` by setting `VOYAGENT_PROVIDER=groq`.

## Tech stack

- **Python 3.10/3.11** with **Poetry** (or `pip`) for dependency management
- **CrewAI** (`crewai[litellm]`) — multi-agent orchestration; LiteLLM enables non-OpenAI providers like Groq
- **LangChain + `langchain-openai`** — `ChatOpenAI` for the OpenAI provider
- **Groq** — free-tier LLM via LiteLLM's `groq/` models
- **Serper.dev** — web search tool (`tools/search_tools.py`)
- **Custom calculator tool** — `tools/calculator_tools.py` (safe AST evaluator)
- **Streamlit** — web UI (`streamlit_app.py`), deployable to Streamlit Community Cloud
- **python-dotenv** — environment variable management

## Repository structure

```
.
├── src/
│   └── voyagent/
│       ├── __main__.py           # CLI entry point (python -m voyagent)
│       ├── crew.py               # TripCrew — orchestration, context wiring, Groq throttle/retry
│       ├── agents.py             # 3 agent definitions (role, goal, tools, LLM, max_iter)
│       ├── tasks.py              # Task prompts with grounding rules
│       ├── config.py             # Env loading, provider/model selection, key validation
│       └── tools/
│           ├── search_tools.py   # Internet search tool (Serper.dev)
│           └── calculator_tools.py  # Calculator tool for budget math
├── streamlit_app.py              # Streamlit web UI
├── .streamlit/config.toml        # Streamlit theme (Tropical Sunset palette)
├── docs/                         # Project documentation
├── .env.example                  # Template for required API keys
├── requirements.txt              # pip dependencies (used by Streamlit Cloud)
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

Copy `.env.example` to `.env` and fill it in. `SERPER_API_KEY` is always required; the LLM key depends on the provider you choose.

```bash
cp .env.example .env
```

**Free, with Groq (recommended for trying it out):**

```env
VOYAGENT_PROVIDER=groq
GROQ_API_KEY=gsk_...          # free at https://console.groq.com/keys
SERPER_API_KEY=...            # free tier at https://serper.dev
```

**With OpenAI (default provider):**

```env
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
```

The app validates these at startup and fails fast with a clear message if a required key is missing.

### 4. Run (CLI)

```bash
python -m voyagent
# or, after `poetry install`:
voyagent
```

You'll be prompted for four inputs:

```
Enter origin: Tunis
Enter candidate destinations (comma-separated): Lisbon, Porto, Barcelona
Enter travel time range: 15 June - 22 June
Enter interests: food, architecture, beach
```

The crew runs and the final trip plan prints to the terminal.

### Web UI

A Streamlit web interface wraps the same crew with a date-range picker and a clean, **abstracted progress display** (friendly phases like "Choosing your destination" — never the raw agent reasoning). After installing dependencies and configuring `.env`:

```bash
streamlit run streamlit_app.py
```

Fill in origin, candidate destinations, travel dates, and interests, then click **Plan my trip ✨**. A 3-phase progress bar runs while the crew works, then the final markdown plan renders in a styled card with a button to download it as `voyagent-trip-plan.md`.

## Deploying to Streamlit Community Cloud

The app is deploy-ready (`requirements.txt` + the `src`-layout path handling in `streamlit_app.py`):

1. Push to GitHub, then on [share.streamlit.io](https://share.streamlit.io) create an app from this repo with **main file** `streamlit_app.py`.
2. In **Advanced settings → Secrets**, add (TOML):
   ```toml
   VOYAGENT_PROVIDER = "groq"
   GROQ_API_KEY = "gsk_..."
   SERPER_API_KEY = "..."
   ```
3. Deploy. Secrets are copied into the environment at startup (`streamlit_app.py`), so the same `config.py` logic works locally and in the cloud.

## Example output

A typical run produces:

- A picked city (from the candidates) with justification: weather for the dates, prices, fit to interests
- A local guide: top attractions, neighborhoods, local customs, seasonal events
- A day-by-day itinerary **covering your exact travel dates**: activities, real hotels and restaurants
- A budget table in one consistent currency
- A packing list tailored to the weather

## Configuration

The provider and model are configured in one place — `src/voyagent/config.py` — and overridable via environment variables (no code change):

| Variable | Purpose | Default |
|---|---|---|
| `VOYAGENT_PROVIDER` | `openai` or `groq` | `openai` |
| `VOYAGENT_MODEL` | model name | `gpt-4o-mini` (openai) / `llama-3.3-70b-versatile` (groq) |
| `VOYAGENT_TEMPERATURE` | sampling temperature | `0.2` |
| `GROQ_STEP_DELAY_SECONDS` | pace agent steps under Groq's free TPM cap (`0` to disable) | `10` |
| `GROQ_NUM_RETRIES` | retries when Groq returns a rate-limit 429 | `8` |
| `CREW_MAX_ATTEMPTS` | retries of the whole crew on Groq's transient tool-call error | `3` |

See [docs/configuration.md](docs/configuration.md) for adding tools and tuning behavior, and [docs/](docs/README.md) for the full documentation set.

> **Note on Groq's free tier:** it caps tokens per minute (≈12k) and per day (≈100k). Voyagent paces and retries calls to stay within the per-minute limit, but a full plan is token-heavy, so the free tier allows only a few runs per day. For faster, higher-volume use, switch `VOYAGENT_MODEL` to a lighter model or upgrade to Groq's Dev tier (and set `GROQ_STEP_DELAY_SECONDS=0`).

## License

Personal / educational project.
