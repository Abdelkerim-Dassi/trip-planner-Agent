# Setup

## Prerequisites

- **Python** 3.10 or 3.11 (the project pins `>=3.10.0,<3.12` in `pyproject.toml`)
- **[Poetry](https://python-poetry.org/)** (recommended) or `pip`
- API keys:
  - **OpenAI** — powers the agents (`gpt-4o-mini`)
  - **Serper.dev** — powers the web search tool

## 1. Clone

```bash
git clone https://github.com/Abdelkerim-Dassi/trip-planner-Agent.git
cd trip-planner-Agent
```

## 2. Install dependencies

With Poetry (recommended — uses the locked dependency set in `poetry.lock`):

```bash
poetry install
poetry shell
```

Or with pip:

```bash
pip install -r requirements.txt
```

## 3. Configure environment variables

The app reads keys from a `.env` file via `python-dotenv`. Copy the template and fill it in:

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=sk-...
OPENAI_ORGANIZATION_ID=org-...   # optional
SERPER_API_KEY=...               # required for web search

# Optional overrides:
# VOYAGENT_MODEL=gpt-4o-mini
# VOYAGENT_TEMPERATURE=0.2
```

Both `OPENAI_API_KEY` and `SERPER_API_KEY` are required. `validate_env()` runs at startup and
exits with a clear message if either is missing — no deep `KeyError` mid-run.

### Where to get keys

| Key | Source |
|---|---|
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `SERPER_API_KEY` | https://serper.dev (free tier available) |

`.env` is git-ignored, so your keys will not be committed.

## 4. Verify

```bash
python -m voyagent
```

If a required key is missing you'll see a `Configuration error:` message and a non-zero exit.
Otherwise you'll see the welcome banner and four input prompts. Proceed to [Usage](usage.md)
for input examples.
