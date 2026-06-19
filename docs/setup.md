# Setup

## Prerequisites

- **Python** 3.10 or 3.11 (the project pins `>=3.10.0,<3.12` in `pyproject.toml`)
- **[Poetry](https://python-poetry.org/)** (recommended) or `pip`
- API keys:
  - An **LLM key** — either **Groq** (free) or **OpenAI**, depending on `VOYAGENT_PROVIDER`
  - **Serper.dev** — powers the web search tool (always required)

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

Or with pip (this is also what Streamlit Community Cloud installs):

```bash
pip install -r requirements.txt
```

`requirements.txt` installs `crewai[litellm]` (LiteLLM is what lets CrewAI talk to non-OpenAI
providers like Groq), the LangChain/OpenAI stack, `requests`, `python-dotenv`, and `streamlit`.

## 3. Configure environment variables

The app reads keys from a `.env` file via `python-dotenv`. Copy the template and fill it in:

```bash
cp .env.example .env
```

Choose **one** LLM provider. `SERPER_API_KEY` is required either way.

**Groq (free):**

```env
VOYAGENT_PROVIDER=groq
GROQ_API_KEY=gsk_...
SERPER_API_KEY=...
```

**OpenAI (default provider):**

```env
OPENAI_API_KEY=sk-...
OPENAI_ORGANIZATION_ID=org-...   # optional
SERPER_API_KEY=...
```

Optional overrides (any provider):

```env
# VOYAGENT_MODEL=llama-3.3-70b-versatile
# VOYAGENT_TEMPERATURE=0.2
# GROQ_STEP_DELAY_SECONDS=10   # pacing for Groq's free TPM cap; 0 to disable
# GROQ_NUM_RETRIES=8
# CREW_MAX_ATTEMPTS=3
```

`validate_env()` runs at startup and exits with a clear message if a required key is missing —
the required keys are `SERPER_API_KEY` plus the chosen provider's key (`GROQ_API_KEY` or
`OPENAI_API_KEY`). No deep `KeyError` mid-run.

### Where to get keys

| Key | Source |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys (free) |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `SERPER_API_KEY` | https://serper.dev (free tier available) |

`.env` is git-ignored, so your keys will not be committed.

## 4. Verify

```bash
python -m voyagent
```

If a required key is missing you'll see a `Configuration error:` message and a non-zero exit.
Otherwise you'll see the welcome banner and four input prompts. Proceed to [Usage](usage.md)
for input examples, or run the web app with `streamlit run streamlit_app.py`.

> **Groq free-tier limits:** Groq caps tokens per minute (~12k) and per day (~100k). Voyagent
> paces and retries requests to stay under the per-minute cap (see
> [Configuration](configuration.md)), but a full plan is token-heavy, so expect only a few runs
> per day on the free tier.
