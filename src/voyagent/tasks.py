"""Task definitions for the trip-planning crew.

To learn more about the Task class, see: https://docs.crewai.com/concepts/tasks

The prompts deliberately push the agents to ground every claim in the
``Search the internet`` tool and to omit anything they cannot verify, since the
underlying model will otherwise invent plausible-but-wrong places, links and
weather.
"""

from textwrap import dedent

from crewai import Task

# Shared grounding rules injected into every task so the agents stay factual.
_GROUNDING_RULES = dedent(
    """
    **Strict accuracy rules — follow exactly:**
    - Use the *Search the internet* tool to verify everything. Base your answer
      only on what the search results actually say.
    - Only mention real, currently-operating places that are located in THIS
      city and its country. Never reference another country's food, landmarks,
      or customs.
    - Links: include a URL only if you copied it verbatim from a search result.
      NEVER make up or guess a URL. If you have no verified link for a place,
      just give its name and neighbourhood — no link.
    - If you cannot verify a detail, leave it out rather than guessing.
    - Write for the traveller: clean markdown, no notes about your own process.
    """
).strip()


class TravelTasks:
    def __tip_section(self) -> str:
        return "If you do your BEST WORK, I'll give you a $10,000 commission!"

    def identify_city(self, agent, origin, cities, travel_dates, interests) -> Task:
        return Task(
            description=dedent(
                f"""
                ***Task**: Pick the single best city for this trip.*

                Choose ONLY from these candidate cities: {cities}.
                Do NOT pick the origin ({origin}) and do NOT pick any city that
                is not in that list.

                Compare the candidates using the *Search the internet* tool to
                check the weather/season for the travel dates, any notable events,
                and rough travel costs from {origin}. Recommend the one city that
                best fits the traveller's interests.

                **Trip parameters:**
                - Origin: {origin}
                - Candidate cities: {cities}
                - Travel dates: {travel_dates}
                - Interests: {interests}

                {_GROUNDING_RULES}

                **Note**: {self.__tip_section()}
                """
            ),
            expected_output=dedent(
                """
                The name of the ONE selected city (from the candidate list) and a
                short justification covering weather for the dates, approximate
                flight cost from the origin, and why it fits the interests.
                """
            ).strip(),
            agent=agent,
        )

    def gather_city_info(self, agent, travel_dates, interests, context=None) -> Task:
        return Task(
            description=dedent(
                f"""
                ***Task**: Build an in-depth guide for the city selected in the
                previous step.*

                Use the city chosen by the City Selection Expert (see context).
                Using the *Search the internet* tool, compile a guide covering the
                top attractions, neighbourhoods, local customs, must-try local
                food, and any events happening during the travel dates. Tailor it
                to the traveller's interests.

                **Trip parameters:**
                - Travel dates: {travel_dates}
                - Interests: {interests}

                {_GROUNDING_RULES}

                **Note**: {self.__tip_section()}
                """
            ),
            expected_output=dedent(
                """
                A comprehensive guide to the SELECTED city: key attractions,
                neighbourhoods, local customs, local food to try, and events
                during the travel dates — every item verified via search and
                located in that city.
                """
            ).strip(),
            agent=agent,
            context=context if context is not None else [],
        )

    def plan_itinerary(self, agent, travel_dates, interests, context=None) -> Task:
        return Task(
            description=dedent(
                f"""
                ***Task**: Build the full day-by-day itinerary for the selected
                city, covering EXACTLY the travel dates: {travel_dates}.*

                Expand the city guide (see context) into one plan that has an
                entry for each day of the trip — count the days from the dates
                above; do not assume any fixed number of days. For each day list
                real, verified attractions, restaurants, and a suggested hotel,
                with a one-line reason for each pick.

                Also include:
                - **Weather**: report it only from a search result for this city
                  and these dates/season. State temperatures in °C consistently
                  (you may add °F in brackets). If you cannot verify a forecast,
                  give a short "typical for the season" note instead of inventing
                  specific numbers.
                - **Packing list** suited to that weather.
                - **Budget**: a markdown table with a category column and an
                  amount column. Use ONE consistent currency symbol throughout
                  (e.g. €120, never a bare 120), and include a total.

                **Trip parameters:**
                - Travel dates: {travel_dates}
                - Interests: {interests}

                {_GROUNDING_RULES}

                **Note**: {self.__tip_section()}
                """
            ),
            expected_output=dedent(
                """
                A complete markdown travel plan for the selected city that starts
                directly with the plan (no preamble): a per-day schedule covering
                exactly the travel dates, a weather summary in °C, a packing list,
                and a budget table in one consistent currency. Every place is real
                and in the selected city; any links are copied from search results.
                """
            ).strip(),
            agent=agent,
            context=context if context is not None else [],
        )
