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

# Rules for the final editing pass, which has no search tool: it must polish what
# it is given without inventing anything new.
_EDITING_RULES = dedent(
    """
    **Strict editing rules — follow exactly:**
    - You are an EDITOR, not a researcher. Work only from the plan you are given
      in the context. You have no search tool.
    - Do NOT add any new place, restaurant, hotel, attraction, link, price,
      date, or weather figure that is not already in the plan. Never invent a URL.
    - You may freely reorganise, retitle, tighten, and rephrase for flow and
      warmth, and remove redundancy — but every fact must already exist in the input.
    - Keep all substance: the per-day schedule, weather, packing list, budget
      table, getting-around info, and signature experiences must all survive.
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

    def curate_experiences(self, agent, travel_dates, interests, context=None) -> Task:
        return Task(
            description=dedent(
                f"""
                ***Task**: Surface the standout, memorable experiences of the
                selected city — the ones that make this trip remarkable.*

                Using the city guide (see context) and the *Search the internet*
                tool, curate 5–8 signature experiences and hidden gems for this
                city, tailored to the traveller's interests. Favour the local,
                distinctive, and memorable over generic tourist checklists.

                For each experience give: a short name, the neighbourhood/area,
                one sentence on why it is special, and the best time to do it
                (time of day or day of week) if relevant.

                **Trip parameters:**
                - Travel dates: {travel_dates}
                - Interests: {interests}

                {_GROUNDING_RULES}

                **Note**: {self.__tip_section()}
                """
            ),
            expected_output=dedent(
                """
                A curated shortlist of 5–8 signature experiences and hidden gems in
                the selected city, each with a name, neighbourhood, a one-line
                reason it stands out, and an ideal time — all verified via search
                and genuinely located in that city.
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
                with a one-line reason for each pick. Weave the signature
                experiences and hidden gems from the Experience Curator (see
                context) into the days where they fit best.

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

    def add_logistics(self, agent, travel_dates, context=None) -> Task:
        return Task(
            description=dedent(
                f"""
                ***Task**: Make the day-by-day plan effortless to follow by adding
                practical logistics.*

                Take the full itinerary (see context) and return THE SAME PLAN
                with logistics woven in — keep every day, place, the weather,
                packing list, and budget intact. Add:
                - A short **Getting Around** section near the top: the main transit
                  options for this city and which ticket or pass makes sense for a
                  trip of these dates ({travel_dates}).
                - Between consecutive stops within each day, a brief note on how to
                  get there (mode of transport and rough travel time).
                - **Book ahead** flags for anything that typically needs advance
                  reservation (timed-entry attractions, popular restaurants).
                - Light timing guidance where it avoids queues or closures.

                Use the *Search the internet* tool to confirm transport options,
                passes, and booking requirements for THIS city — do not guess fares
                or lines.

                {_GROUNDING_RULES}

                **Note**: {self.__tip_section()}
                """
            ),
            expected_output=dedent(
                """
                The complete itinerary, unchanged in substance, now enriched with a
                Getting Around section, transport notes between stops, transit-pass
                advice, and advance-booking flags — all verified for the selected
                city.
                """
            ).strip(),
            agent=agent,
            context=context if context is not None else [],
        )

    def critique_itinerary(self, agent, travel_dates, context=None) -> Task:
        return Task(
            description=dedent(
                f"""
                ***Task**: Stress-test the plan and return a corrected, tighter
                version.*

                Review the full plan (see context) as a demanding travel editor and
                FIX what is wrong, then return the COMPLETE corrected plan (not a
                list of notes). Check specifically:
                - **Reality**: every attraction, restaurant, and hotel is real and
                  located in the selected city. Use the *Search the internet* tool
                  to confirm anything doubtful; remove what you cannot verify.
                - **Geographic flow**: reorder stops within each day so they don't
                  zig-zag across the city; group nearby places together.
                - **Pacing**: each day is realistic, not overstuffed.
                - **Day count**: there is exactly one entry per day of the travel
                  dates ({travel_dates}) — no more, no fewer.
                - **Consistency**: one currency throughout, the budget adds up, and
                  no invented links remain.

                Preserve all the good content, the signature experiences, and the
                logistics; only change what needs fixing.

                {_GROUNDING_RULES}

                **Note**: {self.__tip_section()}
                """
            ),
            expected_output=dedent(
                """
                The complete, corrected travel plan: every place verified and in the
                right city, days flowing geographically with realistic pacing, one
                entry per travel day, consistent currency and a budget that adds up,
                with the signature experiences and logistics retained.
                """
            ).strip(),
            agent=agent,
            context=context if context is not None else [],
        )

    def polish_plan(self, agent, context=None) -> Task:
        return Task(
            description=dedent(
                f"""
                ***Task**: Polish the verified plan into one cohesive, inspiring
                travel document.*

                Take the corrected plan (see context) and reshape it into a
                beautiful final markdown document the traveller will love to read.
                - Open with a short, evocative introduction (2–3 sentences) that
                  names the city and sets the mood — using only what the plan
                  already establishes.
                - Use clear, consistent headings and a clean per-day structure.
                - Keep ALL substance: every day, the Getting Around section, the
                  signature experiences, the weather summary, the packing list, and
                  the budget table.
                - Make the voice warm and motivating, and trim any repetition.

                {_EDITING_RULES}

                **Note**: {self.__tip_section()}
                """
            ),
            expected_output=dedent(
                """
                A polished, cohesive final markdown travel plan that starts directly
                with a short evocative intro, then flows through the per-day
                schedule, getting-around info, signature experiences, weather,
                packing list, and budget table — beautifully formatted and inspiring,
                with no facts, places, or links beyond those already in the plan.
                """
            ).strip(),
            agent=agent,
            context=context if context is not None else [],
        )
