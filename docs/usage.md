# Usage

## Running the planner

From the project root (inside your Poetry/venv shell):

```bash
python -m trip_planner
# or, after `poetry install`, the console script:
trip-planner
```

The CLI first validates your API keys, then prompts for four inputs:

| Prompt | Meaning | Example |
|---|---|---|
| `Enter origin:` | The city you are departing from | `Tunis` |
| `Enter candidate destinations (comma-separated):` | One or more candidate cities | `Lisbon, Porto, Barcelona` |
| `Enter travel time range:` | The date window for the trip | `15 June - 22 June` |
| `Enter interests:` | Themes to optimize the trip around | `food, architecture, beach` |

The City Selection Expert picks one city from the candidate list.

## What happens

Because the `Crew` is built with `verbose=True`, you'll watch each agent reason in real time:
its thoughts, the tool calls it makes (web searches, calculations), and the tool results. When
the run finishes, the final trip plan prints to the terminal:

```
########################
## Here is your Trip plan:
########################

<markdown trip plan>
```

## Expected output

A typical run produces a markdown plan containing:

- **Chosen city** with justification (weather, prices, fit to interests)
- **Local guide** — top attractions, neighborhoods, customs, seasonal events
- **7-day itinerary** — daily activities, specific hotels and restaurants, transit notes
- **Budget breakdown** by category
- **Packing list** tailored to the forecast weather

## Tips

- Runs make multiple LLM calls and several web searches, so a full plan can take a few
  minutes and will consume OpenAI + Serper credits.
- To save the output, redirect or copy it: `python -m trip_planner | tee trip-plan.md`
  (the verbose agent logs are also captured this way).
- Give specific, comma-separated interests for sharper recommendations.
