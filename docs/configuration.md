# Configuration & extension

## Choosing a provider / changing the LLM

Provider and model are configured in **one place** — `src/voyagent/config.py`:

```python
PROVIDER = os.environ.get("VOYAGENT_PROVIDER", "openai").lower()   # "openai" | "groq"
MODEL_NAME = os.environ.get("VOYAGENT_MODEL", _DEFAULT_MODELS.get(PROVIDER, "gpt-4o-mini"))
MODEL_TEMPERATURE = float(os.environ.get("VOYAGENT_TEMPERATURE", "0.2"))
```

`config.build_llm()` returns a single model instance that all seven agents share, so you never
edit per-agent model settings:

- **openai** → `langchain_openai.ChatOpenAI` (default model `gpt-4o-mini`).
- **groq** → `crewai.LLM` using LiteLLM's `groq/<model>` (default `openai/gpt-oss-120b`),
  with `num_retries` so it waits out Groq's rate-limit 429s.

TikTok place extraction (`social.py`) calls LiteLLM directly with `config.litellm_model()`,
which maps the same settings to a LiteLLM model id, so it follows the provider switch too.

To switch (no code change), set environment variables:

```env
VOYAGENT_PROVIDER=groq
VOYAGENT_MODEL=llama-3.1-8b-instant   # optional: a lighter/faster Groq model
```

To add another LiteLLM-supported provider, follow the `groq` branch in `build_llm()` and use the
right `provider/model` prefix, and extend `litellm_model()` to match. For a different LangChain
chat model, change the openai branch.

## Adding a tool

1. Create a function in `src/voyagent/tools/` decorated with CrewAI's `@tool("name")`:

   ```python
   from crewai.tools import tool

   class WeatherTools:
       @tool("Get typical weather")
       def typical(place: str, month: str) -> str:
           """Return typical weather for a place in a given month."""
           ...
   ```

2. Export it from `tools/__init__.py` and attach it to the relevant agent in `agents.py`:

   ```python
   from voyagent.tools import SearchTools, WeatherTools

   tools=[SearchTools.search_internet, WeatherTools.typical]
   ```

The grounded lookups in `travel_info.py` (`typical_weather`, `prayer_times`,
`transfer_options`) and `places.verify_place` are currently exposed only through the MCP server,
not to the crew's agents. Wrapping one of them as a CrewAI tool like the above is a natural
extension — e.g. letting the Travel Concierge use Open-Meteo data instead of web-search
snippets for weather.

To expose a new lookup to assistants as well, add an `@mcp.tool(...)` async function in
`mcp_server.py` (run blocking calls with `_in_thread`); it is then available over stdio, over
`--http`, and at the web app's `/mcp`.

## Tuning prompts / behavior

- **Trip length:** the itinerary follows the **exact travel dates** (no fixed number of
  days). The instruction lives in `tasks.plan_itinerary`, and `tasks.critique_itinerary`
  checks the day count.
- **Grounding rules:** the shared `_GROUNDING_RULES` string in `tasks.py` controls the
  anti-hallucination guardrails (verified places only, no guessed links, omit-when-unsure).
  `_EDITING_RULES` constrains the Final Editor (no new facts). Tighten or relax them there.
- **TikTok inspiration prompt:** `_inspiration_section()` in `tasks.py` controls how the
  Experience Curator treats the traveller's kept spots (reality check, skip with a reason).
- **Search depth:** `SearchTools` returns the top **2** results (`TOP_RESULTS_TO_RETURN`) and
  truncates snippets to `MAX_SNIPPET_CHARS` (150) to keep token use low. Raise either for more
  context per search (at the cost of more tokens). The HTTP timeout is
  `REQUEST_TIMEOUT_SECONDS` in `serper.py`.
- **Discovery size:** `MAX_SPOTS` (10) and `MAX_LINKS` (10) in `social.py`;
  `MAX_DISCOVER_CITIES` (3) in `web/app.py`. Each spot costs ~1 s of Nominatim verification.
- **Agent loop cap:** `_MAX_ITER` (10) in `agents.py` caps each agent's reasoning/tool
  iterations (the Final Editor uses 3).
- **Incentive line:** `TravelTasks.__tip_section()` injects the "$10,000 commission" nudge into
  every task prompt; edit or remove it there.
- **Progress labels:** `PHASES` in `jobs.py` (one per task, in order) drives the web progress
  bar and MCP progress reports. Keep it in step with the tasks if you add or remove one.
- **Verbosity:** the `Crew` and agents run with `verbose=False`. Set `verbose=True` in `crew.py`
  / `agents.py` to see the agents' raw reasoning (the web app deliberately shows only phases).

## Groq free-tier tuning

Used only when `VOYAGENT_PROVIDER=groq`, to stay within Groq's rate limits:

| Variable | Effect | Default |
|---|---|---|
| `GROQ_STEP_DELAY_SECONDS` | sleep between agent steps to respect the tokens-per-minute cap (`0` disables) | `10` |
| `GROQ_NUM_RETRIES` | LiteLLM retries when Groq returns a rate-limit 429 | `8` |
| `CREW_MAX_ATTEMPTS` | retries of the whole crew on Groq's transient `tool_use_failed` error | `3` |

On a paid Groq tier you can set `GROQ_STEP_DELAY_SECONDS=0` to remove the pacing.

## Environment variables

See [Setup](setup.md) for getting keys. The code reads:

| Variable | Used by | Required / default |
|---|---|---|
| `SERPER_API_KEY` | `serper.py` (agent search, TikTok discovery, transfers) | Yes |
| `OPENAI_API_KEY` | openai provider (`ChatOpenAI`, LiteLLM) | Yes if `VOYAGENT_PROVIDER=openai` |
| `GROQ_API_KEY` | groq provider | Yes if `VOYAGENT_PROVIDER=groq` |
| `OPENAI_ORGANIZATION_ID` | OpenAI client (optional) | No |
| `VOYAGENT_PROVIDER` | provider selection | `openai` |
| `VOYAGENT_MODEL` | model selection | provider default |
| `VOYAGENT_TEMPERATURE` | sampling temperature | `0.2` |
| `GROQ_STEP_DELAY_SECONDS` / `GROQ_NUM_RETRIES` / `CREW_MAX_ATTEMPTS` | Groq pacing/retries | `10` / `8` / `3` |
| `VOYAGENT_MAX_ACTIVE_PLANS` | crew runs allowed at once in the web app (others get "busy, try again") | `2` |
| `VOYAGENT_SUPPORT_URL` | donation page shown after a plan and in the footer (hidden if unset) | unset |
| `VOYAGENT_DATA_DIR` | where finished plans are saved for share links (`<dir>/plans/`) | `data` |
| `VOYAGENT_PUBLIC_HOSTS` | extra hostnames the `/mcp` endpoint accepts, comma-separated (Render's `RENDER_EXTERNAL_HOSTNAME` and Hugging Face's `SPACE_HOST` are added automatically) | unset |
| `VOYAGENT_LANGUAGE` | language for place names from OpenStreetMap | `en` |
| `VOYAGENT_USER_AGENT` | `User-Agent` sent to Nominatim (its policy asks for an identifying one) | `ReelTrip/0.2 (open-source AI trip planner)` |
| `HOST` / `PORT` | bind address for `python -m voyagent.web` (the `Dockerfile` sets `0.0.0.0` / `7860`) | `127.0.0.1` / `8000` |
| `RENDER_EXTERNAL_HOSTNAME` / `SPACE_HOST` | set by Render / Hugging Face Spaces; allowed on `/mcp` automatically | — |
