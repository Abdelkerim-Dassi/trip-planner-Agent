# Audit & changelog

This documents the audit performed on the project and the fixes applied during the
"audit and organize" pass. All findings below have been **resolved** in the current code.

## Summary

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | 🔴 High | Tasks wired to the wrong agents; task order reversed | Fixed |
| 2 | 🔴 High | `CalculatorTool.calculate` had a stray `self`; used `eval` | Fixed |
| 3 | 🟠 Medium | `.env_example` missing `SERPER_API_KEY`; failed with `KeyError` | Fixed |
| 4 | 🟠 Medium | No startup validation of required keys | Fixed |
| 5 | 🟡 Low | Two of three agents had no explicit LLM | Fixed |
| 6 | 🟡 Low | Search tool had no timeout / HTTP error handling | Fixed |
| 7 | 🟡 Low | Flat file layout, no package; not installable | Fixed |
| 8 | ⚪ Cosmetic | Typos in user-facing CLI strings | Fixed |

## Details and resolutions

### 1. Mismatched task–agent wiring and ordering (High)

`main.py` assigned the itinerary task to the city-selection agent, `identify_city` to the
local expert, and `gather_city_info` to the concierge — and listed `plan_itinerary` (the final
deliverable) *first*, before a city was even chosen.

**Fixed** in `crew.py`: each agent now owns its matching task, and tasks run in logical order
`identify_city → gather_city_info → plan_itinerary`.

### 2. Calculator `self` bug + unsafe `eval` (High)

`calculate(self, operation)` was decorated `@staticmethod` but still declared `self`, so the
agent's argument bound to `self` and `operation` was never filled. It also used `eval`, which
allows arbitrary code execution.

**Fixed** in `tools/calculator_tools.py`: the `self` parameter is gone, and a restricted AST
evaluator replaces `eval` — only numeric literals and arithmetic operators are permitted. Code
injection (e.g. `__import__("os").system(...)`) is rejected.

### 3. Missing Serper key in env template (Medium)

`search_tools.py` requires `SERPER_API_KEY`, but the template only listed OpenAI keys, so a
fresh setup hit a `KeyError`.

**Fixed:** `.env_example` was replaced by `.env.example`, which documents `SERPER_API_KEY`
plus the optional model overrides.

### 4. No startup key validation (Medium)

A missing key surfaced as a deep `KeyError` mid-run.

**Fixed:** `config.validate_env()` runs at startup (`__main__.main()`) and exits with a clear
`Configuration error:` message listing the missing variables.

### 5. Inconsistent LLM configuration (Low)

Only `city_selection_agent` set an `llm`; the other two relied on CrewAI defaults.

**Fixed:** all three agents share a single model built by `config.build_llm()`
(`gpt-4o-mini`), configurable via `config.py` or env vars.

### 6. Search tool robustness (Low)

The Serper request had no timeout and didn't handle network/HTTP errors.

**Fixed:** the request now has a 15-second timeout, calls `raise_for_status()`, and returns
friendly messages on failure instead of raising.

### 7. Project structure (Low)

The project was a flat set of scripts with no package, not importable or installable.

**Fixed:** moved to a `src/voyagent/` package (src layout) with `config.py`, `crew.py`,
`__main__.py`, and a `tools/` subpackage. `pyproject.toml` declares the package and a
`voyagent` console script; a `requirements.txt` was added for pip users.

### 8. Cosmetic typos (Cosmetic)

"Welcome to **you** AI Travel Crew" / "Here is **you** Trip plan" → corrected to "your".

## Changelog — later changes

After the original audit, the project was extended and rebranded:

- **Rebranded to ReelTrip.** The package, console script, and env-var prefix were renamed
  (`trip_planner` → `voyagent`, `TRIP_PLANNER_*` → `VOYAGENT_*`).
- **Provider-switchable LLM.** `config.build_llm()` now supports Groq (free) alongside OpenAI via
  `VOYAGENT_PROVIDER`; Groq uses `crewai.LLM` over LiteLLM (`crewai[litellm]`).
- **Grounded prompts.** A shared `_GROUNDING_RULES` block makes agents verify via search, use
  real in-country places only, never invent links (verbatim-from-results only), and omit
  unverifiable details. Currency and weather (°C) formatting are enforced.
- **Correct city handoff.** `gather_city_info`/`plan_itinerary` now receive the selected city via
  task `context` instead of the raw candidate list, fixing trips planned for the wrong city.
- **Dynamic trip length.** The hardcoded "7-day" itinerary was replaced with "cover exactly the
  travel dates."
- **Agent tuning.** `max_iter=10`, `allow_delegation=False`, `verbose=False`.
- **Groq free-tier resilience.** Step throttling (`GROQ_STEP_DELAY_SECONDS`), rate-limit retries
  (`GROQ_NUM_RETRIES`), and whole-crew retry on `tool_use_failed` (`CREW_MAX_ATTEMPTS`); search
  results trimmed to 2 with truncated snippets to limit tokens.
- **Streamlit web app.** `streamlit_app.py` with a date-range picker, abstracted 3-phase progress
  (no raw reasoning), a Tropical Sunset theme, and Streamlit Community Cloud deploy support
  (secrets copied into the environment at startup).
- **Dependencies.** `requirements.txt` switched to `crewai[litellm]` and **dropped the unused
  `unstructured` and `pyowm`** packages.
- **Four refinement agents.** The crew grew from three to seven agents: an Experience Curator
  (after the Local Expert) and, after the Travel Concierge, a Logistics Planner, an Itinerary
  Critic, and a tool-less Final Editor bound by `_EDITING_RULES` (no new facts).

### 2026-10-25 — Web app, TikTok discovery, MCP server

- **Seven-agent crew, documented.** `agents.py`, `tasks.py`, and `crew.py` run seven sequential
  agents (City Selection Expert, Local Expert, Experience Curator, Travel Concierge, Logistics
  Planner, Itinerary Critic, Final Editor); the docs no longer describe three agents/tasks.
  `TripCrew` takes an optional `inspiration` argument, passed to the curator task and rendered by
  `_inspiration_section()` in `tasks.py` with a reality check for each place.
- **Streamlit removed.** `streamlit_app.py` and `.streamlit/` were deleted. They are replaced by
  a **FastAPI web app** in `src/voyagent/web/` (`python -m voyagent.web`): `/` planner page,
  `/p/{id}` server-rendered share page, `/api/discover`, `/api/plans`, `/api/plans/{id}`,
  `/healthz`, OpenAPI docs at `/api/docs`, and the MCP server mounted at `/mcp`. The front end
  is Jinja2 templates plus vanilla JS with a Leaflet map (no build step). Plan runs go through
  `jobs.PlanJob` (background thread, seven abstracted `PHASES`), capped by
  `VOYAGENT_MAX_ACTIVE_PLANS`; finished plans are saved under `VOYAGENT_DATA_DIR`.
- **TikTok discovery** (`social.py`): Serper search of `site:tiktok.com` → LLM extracts the named
  places (LiteLLM JSON mode, `config.litellm_model()`) → Nominatim verification in the
  destination's country → spots ranked by video mentions, each linked to its videos.
  `spots_from_links` handles pasted links. No scraping and no video downloads.
- **New grounded modules.** `serper.py` (shared, per-query cached Serper client; the agents'
  `search_tools.py` now uses it), `places.py` (OpenStreetMap Nominatim verification with a
  ~1 req/s throttle, caching, and distances), `travel_info.py` (`typical_weather` from the
  Open-Meteo archive, `prayer_times` from AlAdhan, `transfer_options` via Serper).
- **MCP server** (`mcp_server.py`): MCP SDK 2.x `MCPServer` with seven tools
  (`trending_spots`, `spots_from_tiktok_links`, `verify_place`, `typical_weather`,
  `prayer_times`, `transfer_options`, `plan_trip`), over stdio or `--http`, and at `/mcp` in the
  web app with DNS-rebinding protection (`SPACE_HOST`, `VOYAGENT_PUBLIC_HOSTS`).
- **Hosting.** A `Dockerfile` runs the web app on port 7860 for Hugging Face Spaces (Docker SDK)
  or any container host. New env vars: `VOYAGENT_MAX_ACTIVE_PLANS`, `VOYAGENT_SUPPORT_URL`,
  `VOYAGENT_DATA_DIR`, `VOYAGENT_PUBLIC_HOSTS`, `VOYAGENT_LANGUAGE` (plus `VOYAGENT_USER_AGENT`,
  `HOST`, `PORT`).
- **Dependencies.** `streamlit` removed from `requirements.txt`; `fastapi`, `uvicorn[standard]`,
  `jinja2`, and `mcp>=2.3,<3` added to `requirements.txt` and `pyproject.toml`, which also gained the
  `voyagent-web` and `voyagent-mcp` console scripts. `poetry.lock` has **not** been regenerated
  yet — Poetry users must run `poetry lock` first.

## Remaining suggestions (not yet done)

- Add automated tests (e.g. for the calculator evaluator, `validate_env`, provider selection
  in `build_llm`, the web API, and the TikTok/place-verification pipeline with mocked HTTP).
- Expose the grounded lookups (`travel_info.typical_weather`, `places.verify_place`) to the
  crew's agents as CrewAI tools; today only the MCP server uses them.
- Reconcile `pyproject.toml` with `requirements.txt` (it still lists the now-unused `unstructured`
  and `pyowm`) and regenerate `poetry.lock`.
