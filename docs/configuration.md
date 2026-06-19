# Configuration & extension

## Choosing a provider / changing the LLM

Provider and model are configured in **one place** — `src/voyagent/config.py`:

```python
PROVIDER = os.environ.get("VOYAGENT_PROVIDER", "openai").lower()   # "openai" | "groq"
MODEL_NAME = os.environ.get("VOYAGENT_MODEL", _DEFAULT_MODELS.get(PROVIDER, "gpt-4o-mini"))
MODEL_TEMPERATURE = float(os.environ.get("VOYAGENT_TEMPERATURE", "0.2"))
```

`config.build_llm()` returns a single model instance that all three agents share, so you never
edit per-agent model settings:

- **openai** → `langchain_openai.ChatOpenAI` (default model `gpt-4o-mini`).
- **groq** → `crewai.LLM` using LiteLLM's `groq/<model>` (default `llama-3.3-70b-versatile`),
  with `num_retries` so it waits out Groq's rate-limit 429s.

To switch (no code change), set environment variables:

```env
VOYAGENT_PROVIDER=groq
VOYAGENT_MODEL=llama-3.1-8b-instant   # optional: a lighter/faster Groq model
```

To add another LiteLLM-supported provider, follow the `groq` branch in `build_llm()` and use the
right `provider/model` prefix. For a different LangChain chat model, change the openai branch.

## Adding a tool

1. Create a function in `src/voyagent/tools/` decorated with CrewAI's `@tool("name")`:

   ```python
   from crewai.tools import tool

   class WeatherTools:
       @tool("Get weather forecast")
       def forecast(location: str) -> str:
           """Return a weather forecast for the given location."""
           ...
   ```

2. Export it from `tools/__init__.py` and attach it to the relevant agent in `agents.py`:

   ```python
   from voyagent.tools import SearchTools, WeatherTools

   tools=[SearchTools.search_internet, WeatherTools.forecast]
   ```

A dedicated weather tool is a natural extension — it would let the Travel Concierge report
forecasts without relying on web-search snippets. (Note: `requirements.txt` no longer ships
`pyowm`/`unstructured`; add the dependency you need.)

## Tuning prompts / behavior

- **Trip length:** the itinerary now follows the **exact travel dates** (no fixed number of
  days). The instruction lives in `tasks.plan_itinerary`.
- **Grounding rules:** the shared `_GROUNDING_RULES` string in `tasks.py` controls the
  anti-hallucination guardrails (verified places only, no guessed links, omit-when-unsure).
  Tighten or relax them there.
- **Search depth:** `SearchTools` returns the top **2** results (`TOP_RESULTS_TO_RETURN`) and
  truncates snippets to `MAX_SNIPPET_CHARS` (150) to keep token use low. Raise either for more
  context per search (at the cost of more tokens). Adjust `REQUEST_TIMEOUT_SECONDS` for the HTTP
  timeout.
- **Agent loop cap:** `_MAX_ITER` (10) in `agents.py` caps each agent's reasoning/tool
  iterations.
- **Incentive line:** `TravelTasks.__tip_section()` injects the "$10,000 commission" nudge into
  every task prompt; edit or remove it there.
- **Verbosity:** the `Crew` and agents run with `verbose=False`. Set `verbose=True` in `crew.py`
  / `agents.py` to see the agents' raw reasoning (the web app deliberately hides it regardless).

## Groq free-tier tuning

Used only when `VOYAGENT_PROVIDER=groq`, to stay within Groq's rate limits:

| Variable | Effect | Default |
|---|---|---|
| `GROQ_STEP_DELAY_SECONDS` | sleep between agent steps to respect the tokens-per-minute cap (`0` disables) | `10` |
| `GROQ_NUM_RETRIES` | LiteLLM retries when Groq returns a rate-limit 429 | `8` |
| `CREW_MAX_ATTEMPTS` | retries of the whole crew on Groq's transient `tool_use_failed` error | `3` |

On a paid Groq tier you can set `GROQ_STEP_DELAY_SECONDS=0` to remove the pacing.

## Environment variables

See [Setup](setup.md) for the full list. The code reads:

| Variable | Used by | Required |
|---|---|---|
| `SERPER_API_KEY` | `SearchTools.search_internet` | Yes |
| `OPENAI_API_KEY` | openai provider (`ChatOpenAI`) | Yes if `VOYAGENT_PROVIDER=openai` |
| `GROQ_API_KEY` | groq provider | Yes if `VOYAGENT_PROVIDER=groq` |
| `OPENAI_ORGANIZATION_ID` | OpenAI client (optional) | No |
| `VOYAGENT_PROVIDER` | provider selection | No (default `openai`) |
| `VOYAGENT_MODEL` | model selection | No (provider default) |
| `VOYAGENT_TEMPERATURE` | sampling temperature | No (default `0.2`) |
| `GROQ_STEP_DELAY_SECONDS` / `GROQ_NUM_RETRIES` / `CREW_MAX_ATTEMPTS` | Groq pacing/retries | No |
