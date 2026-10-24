# Setup

## Prerequisites

- **Python** 3.10 or 3.11 (the project pins `>=3.10.0,<3.12` in `pyproject.toml`; the
  `Dockerfile` uses 3.11)
- **[Poetry](https://python-poetry.org/)** (recommended) or `pip`
- API keys:
  - An **LLM key** — either **Groq** (free) or **OpenAI**, depending on `VOYAGENT_PROVIDER`
  - **Serper.dev** — powers web search and TikTok discovery (always required)
- No keys are needed for OpenStreetMap Nominatim, Open-Meteo, or AlAdhan.

## 1. Clone

```bash
git clone https://github.com/Abdelkerim-Dassi/trip-planner-Agent.git
cd trip-planner-Agent
```

## 2. Install dependencies

With Poetry (recommended):

```bash
poetry lock      # needed for now: see the note below
poetry install
poetry shell
```

> **Note:** `pyproject.toml` gained `fastapi`, `uvicorn[standard]`, `jinja2`, and `mcp`,
> but `poetry.lock` has **not been regenerated yet**. Run
> `poetry lock` before `poetry install`, or Poetry will refuse to install from the stale lock.

Or with pip (this is also what the `Dockerfile` installs):

```bash
pip install -r requirements.txt
```

`requirements.txt` installs `crewai[litellm]` (LiteLLM is what lets CrewAI talk to non-OpenAI
providers like Groq, and what TikTok place extraction calls directly), the LangChain/OpenAI
stack, `requests`, `python-dotenv`, and for the web app and MCP server `fastapi`,
`uvicorn[standard]`, `jinja2`, and `mcp>=2.3,<3` (the MCP Python SDK 2.x).

`pip install -r requirements.txt` installs only the dependencies, not the `voyagent` package
itself (src layout), so put `src` on the path when running the modules — e.g.
`PYTHONPATH=src python -m voyagent.web`, as the `Dockerfile` does. `poetry install` installs
the package plus the `voyagent`, `voyagent-web`, and `voyagent-mcp` console scripts.

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

Web app / hosting options (`VOYAGENT_MAX_ACTIVE_PLANS`, `VOYAGENT_SUPPORT_URL`,
`VOYAGENT_DATA_DIR`, `VOYAGENT_PUBLIC_HOSTS`, `VOYAGENT_LANGUAGE`, ...) are listed in
[Configuration](configuration.md#environment-variables).

`validate_env()` runs at startup and exits with a clear message if a required key is missing —
the required keys are `SERPER_API_KEY` plus the chosen provider's key (`GROQ_API_KEY` or
`OPENAI_API_KEY`). No deep `KeyError` mid-run. The web app starts without them but answers
`503` with the same message on `/api/discover` and `/api/plans`.

### Where to get keys

| Key | Source |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys (free) |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `SERPER_API_KEY` | https://serper.dev (free tier available) |

`.env` is git-ignored, so your keys will not be committed (as is `data/`, where the web app
saves shared plans).

## 4. Verify

```bash
python -m voyagent
```

If a required key is missing you'll see a `Configuration error:` message and a non-zero exit.
Otherwise you'll see the welcome banner and four input prompts. Proceed to [Usage](usage.md)
for input examples, or run the web app with `python -m voyagent.web` and open
http://127.0.0.1:8000 (`/healthz` should return `{"ok": true}`).

## 5. Docker (optional)

```bash
docker build -t voyagent .
docker run -p 7860:7860 --env-file .env voyagent    # http://localhost:7860
```

The image runs `python -m voyagent.web` on port 7860 as user 1000, which is what Hugging Face
Spaces (Docker SDK) expects; see the root [README](../README.md#deploying-for-free-hugging-face-spaces)
for the Space setup.

> **Groq free-tier limits:** Groq caps tokens per minute (~12k) and per day (~100k). Voyagent
> paces and retries requests to stay under the per-minute cap (see
> [Configuration](configuration.md)), but a full seven-agent plan is token-heavy, so expect
> only a few runs per day on the free tier.
