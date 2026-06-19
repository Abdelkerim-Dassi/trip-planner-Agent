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

- **Rebranded to Voyagent.** The package, console script, and env-var prefix were renamed
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

## Remaining suggestions (not yet done)

- Add automated tests (e.g. for the calculator evaluator, `validate_env`, and provider selection
  in `build_llm`).
- Add a dedicated weather tool (add the weather SDK of your choice as a dependency).
- Reconcile `pyproject.toml` with `requirements.txt` (it still lists the now-unused `unstructured`
  and `pyowm`).
