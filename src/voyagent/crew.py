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


def _is_transient_tool_error(exc) -> bool:
    """True for Groq's intermittent malformed-tool-call rejection.

    Groq's Llama models occasionally emit a tool call in the wrong format, which
    Groq rejects server-side (``tool_use_failed``) before CrewAI can re-prompt.
    The same request usually succeeds on a fresh attempt.
    """
    msg = str(exc).lower()
    return (
        "tool_use_failed" in msg
        or "failed to call a function" in msg
        or "please adjust your prompt" in msg
    )


class TripCrew:
    def __init__(self, origin, cities, date_range, interests):
        self.origin = origin
        self.cities = cities
        self.date_range = date_range
        self.interests = interests

    def run(self, step_callback=None, task_callback=None):
        # On Groq's free tier, pace each step to stay under the tokens-per-minute
        # cap. GROQ_STEP_DELAY_SECONDS=0 disables it (e.g. on a paid tier).
        if config.PROVIDER == "groq":
            delay = float(os.environ.get("GROQ_STEP_DELAY_SECONDS", "10"))
            if delay > 0:
                step_callback = _throttled(step_callback, delay)

        # Retry the whole crew on Groq's intermittent malformed-tool-call error.
        attempts = int(os.environ.get("CREW_MAX_ATTEMPTS", "3"))
        for attempt in range(1, attempts + 1):
            try:
                return self._kickoff(step_callback, task_callback)
            except Exception as exc:
                if attempt == attempts or not _is_transient_tool_error(exc):
                    raise
                time.sleep(2)  # brief pause, then rebuild and try again

    def _kickoff(self, step_callback, task_callback):
        """Build a fresh crew and run it once."""
        agents = TravelAgents()
        tasks = TravelTasks()

        # Each agent owns the task that matches its role.
        city_selector = agents.city_selection_agent()
        local_expert = agents.local_expert()
        curator = agents.experience_curator()
        concierge = agents.travel_concierge()
        logistics = agents.logistics_planner()
        critic = agents.itinerary_critic()
        editor = agents.final_editor()

        # Each step's output flows forward via task context (not by re-passing raw
        # inputs), so every downstream agent works from the verified result of the
        # previous step. The selected city is carried by identify_city's output,
        # which keeps the rest of the crew from planning the wrong (or origin) city.
        #
        # The plan is progressively refined: the concierge drafts it, the logistics
        # planner makes it easy to follow, the critic corrects and tightens it, and
        # the editor polishes the verified result into the final document. Each of
        # those steps returns the *complete* plan, so the next can refine it whole.
        identify_city = tasks.identify_city(
            city_selector, self.origin, self.cities, self.date_range, self.interests
        )
        gather_city_info = tasks.gather_city_info(
            local_expert, self.date_range, self.interests, context=[identify_city]
        )
        curate_experiences = tasks.curate_experiences(
            curator, self.date_range, self.interests, context=[gather_city_info]
        )
        plan_itinerary = tasks.plan_itinerary(
            concierge,
            self.date_range,
            self.interests,
            context=[gather_city_info, curate_experiences],
        )
        add_logistics = tasks.add_logistics(
            logistics, self.date_range, context=[plan_itinerary]
        )
        critique_itinerary = tasks.critique_itinerary(
            critic, self.date_range, context=[add_logistics]
        )
        polish_plan = tasks.polish_plan(editor, context=[critique_itinerary])

        # Tasks run in logical order: pick the city, learn about it, curate the
        # standout experiences, draft the plan, add logistics, critique/correct,
        # then polish. Optional callbacks let a UI observe progress: step_callback
        # fires on each agent step, task_callback when each task finishes.
        crew = Crew(
            agents=[
                city_selector,
                local_expert,
                curator,
                concierge,
                logistics,
                critic,
                editor,
            ],
            tasks=[
                identify_city,
                gather_city_info,
                curate_experiences,
                plan_itinerary,
                add_logistics,
                critique_itinerary,
                polish_plan,
            ],
            verbose=False,
            step_callback=step_callback,
            task_callback=task_callback,
        )

        return crew.kickoff()
