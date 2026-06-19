"""Agent definitions for the trip-planning crew.

All three agents share the model configured in :mod:`voyagent.config`. Goals and
backstories stress verified, local-only information because the model otherwise
tends to invent places and facts. ``max_iter`` caps each agent's tool loop, which
also keeps token use within Groq's free-tier budget.
"""

from crewai import Agent

from voyagent.config import build_llm
from voyagent.tools import CalculatorTool, SearchTools

# Cap on reasoning/tool iterations per agent — enough to research thoroughly,
# low enough to stay focused and within the token budget.
_MAX_ITER = 10


class TravelAgents:
    def __init__(self):
        # Build the shared LLM once and reuse it across agents.
        self._llm = build_llm()

    def city_selection_agent(self) -> Agent:
        return Agent(
            role="City Selection Expert",
            goal=(
                "Pick the single best city from the candidate list for the given "
                "dates and interests, using only facts found via web search"
            ),
            backstory=(
                "A meticulous travel analyst who compares destinations on real "
                "weather, events, and prices. You never recommend a city you "
                "haven't checked, and you only choose from the candidates given."
            ),
            tools=[SearchTools.search_internet, CalculatorTool.calculate],
            llm=self._llm,
            max_iter=_MAX_ITER,
            allow_delegation=False,
            verbose=False,
        )

    def local_expert(self) -> Agent:
        return Agent(
            role="Local Expert at this city",
            goal=(
                "Describe the selected city accurately using only verified, "
                "local information about its real attractions, food, and customs"
            ),
            backstory=(
                "A lifelong resident and guide of the selected city. You speak "
                "only about places that genuinely exist in this city and its "
                "country, and you check details by searching before sharing them."
            ),
            tools=[SearchTools.search_internet],
            llm=self._llm,
            max_iter=_MAX_ITER,
            allow_delegation=False,
            verbose=False,
        )

    def travel_concierge(self) -> Agent:
        return Agent(
            role="Amazing Travel Concierge",
            goal=(
                "Turn the city guide into an accurate day-by-day itinerary, "
                "weather summary, packing list, and budget — all grounded in "
                "verified, local facts"
            ),
            backstory=(
                "A precise travel planner who builds itineraries only from real, "
                "verified places in the chosen city. You never fabricate links, "
                "prices, or weather, and you keep currency and units consistent."
            ),
            tools=[SearchTools.search_internet, CalculatorTool.calculate],
            llm=self._llm,
            max_iter=_MAX_ITER,
            allow_delegation=False,
            verbose=False,
        )
