"""Crew orchestration: wires the three agents to their tasks and runs them."""

import os
import time

from crewai import Crew

from voyagent import config
from voyagent.agents import TravelAgents
from voyagent.tasks import TravelTasks


def _throttled(step_callback, delay_seconds):
    """Wrap a step callback so each agent step pauses ``delay_seconds``.

    Groq's free tier caps tokens-per-minute; pacing the ReAct loop keeps a run
    under that ceiling instead of relying solely on retry-after backoff.
    """

    def _callback(step_output=None):
        if step_callback is not None:
            step_callback(step_output)
        time.sleep(delay_seconds)

    return _callback


class TripCrew:
    def __init__(self, origin, cities, date_range, interests):
        self.origin = origin
        self.cities = cities
        self.date_range = date_range
        self.interests = interests

    def run(self, step_callback=None, task_callback=None):
        agents = TravelAgents()
        tasks = TravelTasks()

        # Each agent owns the task that matches its role.
        city_selector = agents.city_selection_agent()
        local_expert = agents.local_expert()
        concierge = agents.travel_concierge()

        identify_city = tasks.identify_city(
            city_selector, self.origin, self.cities, self.date_range, self.interests
        )
        gather_city_info = tasks.gather_city_info(
            local_expert, self.cities, self.date_range, self.interests
        )
        plan_itinerary = tasks.plan_itinerary(
            concierge, self.cities, self.date_range, self.interests
        )

        # On Groq's free tier, pace each step to stay under the tokens-per-minute
        # cap. GROQ_STEP_DELAY_SECONDS=0 disables it (e.g. on a paid tier).
        if config.PROVIDER == "groq":
            delay = float(os.environ.get("GROQ_STEP_DELAY_SECONDS", "5"))
            if delay > 0:
                step_callback = _throttled(step_callback, delay)

        # Tasks run in logical order: pick the city, learn about it, then plan.
        # Optional callbacks let a UI observe progress: step_callback fires on
        # each agent step, task_callback when each of the three tasks finishes.
        crew = Crew(
            agents=[city_selector, local_expert, concierge],
            tasks=[identify_city, gather_city_info, plan_itinerary],
            verbose=True,
            step_callback=step_callback,
            task_callback=task_callback,
        )

        return crew.kickoff()
