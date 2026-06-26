"""Agent definitions for the trip-planning crew.

All agents share the model configured in :mod:`voyagent.config`. Goals and
backstories stress verified, local-only information because the model otherwise
tends to invent places and facts. ``max_iter`` caps each agent's tool loop, which
also keeps token use within Groq's free-tier budget.

The crew runs seven agents in sequence: a City Selection Expert and Local Expert
research the trip, an Experience Curator surfaces standout local moments, a
Travel Concierge drafts the day-by-day plan, a Logistics Planner makes it easy to
follow, an Itinerary Critic corrects and tightens it, and a Final Editor polishes
the result into one inspiring document. See :mod:`voyagent.crew` for the wiring.
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

    def experience_curator(self) -> Agent:
        return Agent(
            role="Local Experience Curator",
            goal=(
                "Surface the signature experiences and hidden gems of the selected "
                "city — the memorable, local-only moments a typical tourist would "
                "miss — matched to the traveller's interests, all verified by search"
            ),
            backstory=(
                "A tastemaker with an insider's little black book for this city. "
                "You skip the obvious tourist traps and uncover the standout "
                "experiences locals actually love — but you only recommend places "
                "you have confirmed are real and currently operating via search."
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

    def logistics_planner(self) -> Agent:
        return Agent(
            role="Travel Logistics Planner",
            goal=(
                "Make the itinerary effortless to follow: add how to get between "
                "each stop, the right transit passes, what to book in advance, and "
                "sensible timing — all verified for this specific city"
            ),
            backstory=(
                "A logistics specialist who has moved thousands of travellers "
                "around this city. You know its metro, trams, and walking routes, "
                "and you only state transport options and booking requirements you "
                "have confirmed by search — never guessed."
            ),
            tools=[SearchTools.search_internet, CalculatorTool.calculate],
            llm=self._llm,
            max_iter=_MAX_ITER,
            allow_delegation=False,
            verbose=False,
        )

    def itinerary_critic(self) -> Agent:
        return Agent(
            role="Meticulous Itinerary Critic",
            goal=(
                "Stress-test the draft plan and return a corrected, improved "
                "version: verify every place is real and in the right city, fix "
                "geographic flow so days don't zig-zag, ensure realistic pacing, "
                "and confirm the day count matches the travel dates exactly"
            ),
            backstory=(
                "A demanding travel editor who has caught countless errors in "
                "draft itineraries: invented restaurants, a museum on the wrong "
                "side of town scheduled back-to-back with one across it, days that "
                "don't add up. You fix these issues and hand back a tighter plan, "
                "checking anything doubtful with search before keeping it."
            ),
            tools=[SearchTools.search_internet, CalculatorTool.calculate],
            llm=self._llm,
            max_iter=_MAX_ITER,
            allow_delegation=False,
            verbose=False,
        )

    def final_editor(self) -> Agent:
        return Agent(
            role="Travel Storyteller and Editor",
            goal=(
                "Polish the verified plan into one cohesive, beautifully formatted, "
                "and inspiring travel document — without adding any new facts, "
                "places, links, or numbers beyond what is already in the plan"
            ),
            backstory=(
                "An award-winning travel writer with an eye for clean structure "
                "and a warm, motivating voice. You make a plan a joy to read, but "
                "you are strictly an editor: you reorganise and rephrase what you "
                "are given and never invent new places, prices, or links."
            ),
            tools=[],
            llm=self._llm,
            max_iter=3,
            allow_delegation=False,
            verbose=False,
        )
