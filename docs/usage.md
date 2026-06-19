# Usage

Voyagent runs two ways: an interactive **CLI** and a **Streamlit web app**. Both drive the same
`TripCrew`.

## CLI

From the project root (inside your Poetry/venv shell):

```bash
python -m voyagent
# or, after `poetry install`, the console script:
voyagent
```

The CLI first validates your API keys, then prompts for four inputs:

| Prompt | Meaning | Example |
|---|---|---|
| `Enter origin:` | The city you are departing from | `Tunis` |
| `Enter candidate destinations (comma-separated):` | One or more candidate cities | `Lisbon, Porto, Barcelona` |
| `Enter travel time range:` | The date window for the trip | `15 June - 22 June` |
| `Enter interests:` | Themes to optimize the trip around | `food, architecture, beach` |

The City Selection Expert picks **one** city from the candidate list (never the origin), and
the rest of the crew plans for that city. When the run finishes, the final trip plan prints to
the terminal:

```
########################
## Here is your Trip plan:
########################

<markdown trip plan>
```

The crew runs with `verbose=False`, so the agents' internal reasoning is not dumped to the
console — you get progress from CrewAI plus the final plan.

## Web app

```bash
streamlit run streamlit_app.py
```

- Pick your dates on a **calendar range picker** and fill in origin, candidate destinations, and
  interests.
- While the crew works, a **3-phase progress bar** shows friendly status — *Choosing your
  destination → Researching the city → Crafting your itinerary* — and never the raw agent
  reasoning.
- The finished plan renders in a styled card with a **Download (Markdown)** button
  (`voyagent-trip-plan.md`).

The web app is also deployable to Streamlit Community Cloud — see the README's deploy section.

## Expected output

A typical run produces a markdown plan containing:

- **Chosen city** (from your candidates) with justification (weather for the dates, prices, fit)
- **Local guide** — top attractions, neighborhoods, customs, seasonal events
- **Day-by-day itinerary** covering **exactly your travel dates** (not a fixed length): daily
  activities, specific hotels and restaurants
- **Weather** summary in °C
- **Budget table** in one consistent currency
- **Packing list** tailored to the weather

Because the prompts force grounding in search results, the model omits details it can't verify
(e.g. it will skip a link rather than guess one).

## Tips

- Runs make multiple LLM calls and several web searches, so a full plan takes a few minutes —
  longer on Groq's free tier because steps are paced to respect the rate limit.
- On Groq's free tier you only get a few full runs per day (token cap). For more, switch to a
  lighter `VOYAGENT_MODEL`, or upgrade the Groq tier and set `GROQ_STEP_DELAY_SECONDS=0`.
- Give specific, comma-separated interests for sharper recommendations.
- To save CLI output: `python -m voyagent | tee trip-plan.md`.
