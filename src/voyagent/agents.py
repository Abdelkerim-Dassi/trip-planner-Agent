"""Agent definitions for the trip-planning crew.

All three agents share the model configured in :mod:`voyagent.config`.
"""

from crewai import Agent

from voyagent.config import build_llm
from voyagent.tools import CalculatorTool, SearchTools


class TravelAgents:
    def __init__(self):
        # Build the shared LLM once and reuse it across agents.
        self._llm = build_llm()

    def city_selection_agent(self) -> Agent:
        return Agent(
            role="City Selection Expert",
            goal="Select the best city based on weather, season, and prices",
            backstory="An expert in analyzing travel data to pick ideal destinations",
            tools=[SearchTools.search_internet, CalculatorTool.calculate],
            llm=self._llm,
            verbose=True,
        )

    def local_expert(self) -> Agent:
        return Agent(
            role="Local Expert at this city",
            goal="Provide the BEST insights about the selected city",
            backstory=(
                "A knowledgeable local guide with extensive information about the "
                "city, its attractions and customs"
            ),
            tools=[SearchTools.search_internet],
            llm=self._llm,
            verbose=True,
        )

    def travel_concierge(self) -> Agent:
        return Agent(
            role="Amazing Travel Concierge",
            goal=(
                "Create the most amazing travel itineraries with budget and packing "
                "suggestions for the city"
            ),
            backstory=(
                "Specialist in travel planning and logistics with decades of experience"
            ),
            tools=[SearchTools.search_internet, CalculatorTool.calculate],
            llm=self._llm,
            verbose=True,
        )
