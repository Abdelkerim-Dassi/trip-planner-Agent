"""Background jobs shared by the web app and the MCP server.

A plan takes a minute or two and an itinerary check up to a minute, so callers
start a job in a thread and poll it. Jobs only expose abstracted progress
(which phase is running, which place is being checked), never a model's raw
reasoning.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date

from voyagent import config

log = logging.getLogger(__name__)

#: One phase per crew task, in run order (see voyagent.crew).
PHASES = [
    ("✈️", "Choosing your destination"),
    ("🗺️", "Researching the city"),
    ("✨", "Uncovering hidden gems"),
    ("🧳", "Crafting your itinerary"),
    ("🚇", "Sorting out the logistics"),
    ("🔍", "Checking every place on the map"),
    ("📖", "Checking opening days"),
]


#: Added to the interests for the crew when the traveller asks for halal food
#: and prayer times (quick mode adds verified facts instead, see quick_plan).
HALAL_NOTE = (
    "; halal food only (no pork, no alcohol-led venues), and plan around the five "
    "daily prayers, with Friday midday prayer kept free"
)

#: Languages a plan can be written in (the form's choices).
LANGUAGES = {"en": "English", "fr": "French", "ar": "Arabic"}


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _friendly(exc: Exception, what: str) -> str:
    """A message for the visitor: never a provider's raw error text."""
    log.warning("%s job failed: %s: %s", what, type(exc).__name__, str(exc)[:300])
    if isinstance(exc, RuntimeError) and type(exc).__module__.startswith("voyagent"):
        return str(exc)  # our own errors are already written for the visitor
    if type(exc) is RuntimeError:
        return str(exc)
    if "RateLimit" in type(exc).__name__ or "ServiceUnavailable" in type(exc).__name__:
        return "The free AI models are at their limit right now. Please try again in a few minutes."
    return f"The {what} couldn't finish ({type(exc).__name__}). Please try again in a minute."


@dataclass
class PlanJob:
    origin: str
    cities: str
    travel_dates: str
    interests: str
    inspiration: str = ""
    halal: bool = False  # halal food and prayer-time aware plan
    language: str = "en"
    id: str = field(default_factory=_new_id)
    status: str = "queued"  # queued | running | done | error
    completed: int = 0
    steps: int = 0
    detail: str = ""  # what is being checked right now
    result: str = ""
    error: str = ""
    checks: list = field(default_factory=list)  # per-sight summary (share images)
    review: dict | None = None  # the full check report (voyagent.review)
    created: float = field(default_factory=time.time)

    @property
    def phase(self) -> str:
        icon, label = PHASES[min(self.completed, len(PHASES) - 1)]
        return f"{icon} {label}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "phase": self.phase,
            "detail": self.detail,
            "completed": self.completed,
            "total": len(PHASES),
            "steps": self.steps,
            "result": self.result,
            "error": self.error,
            "checks": self.checks,
            "review": self.review,
            "created": self.created,
            "request": {
                "origin": self.origin,
                "cities": self.cities,
                "travel_dates": self.travel_dates,
                "interests": self.interests,
                "halal": self.halal,
                "language": self.language,
            },
        }

    def run(self) -> None:
        """Write the plan, then check it, in the calling thread."""
        def step_callback(_step=None) -> None:
            self.steps += 1

        def task_callback(_task=None) -> None:
            self.completed = min(self.completed + 1, len(PHASES))

        self.status = "running"
        try:
            if config.PLAN_MODE == "quick":
                from voyagent.quick_plan import quick_plan

                def on_phase(index: int) -> None:
                    self.completed = max(self.completed, min(index + 1, len(PHASES)))

                self.result = quick_plan(
                    self.origin, self.cities, self.travel_dates, self.interests,
                    self.inspiration, on_phase=on_phase, halal=self.halal,
                    language=LANGUAGES.get(self.language, "English"),
                )
            else:
                from voyagent.crew import TripCrew  # heavy import; only when planning

                interests = self.interests + (HALAL_NOTE if self.halal else "")
                crew = TripCrew(
                    self.origin, self.cities, self.travel_dates, interests, self.inspiration
                )
                result = crew.run(step_callback=step_callback, task_callback=task_callback)
                self.result = getattr(result, "raw", None) or str(result)
            self.completed = len(PHASES) - 2
            from voyagent import review
            from voyagent.hours import chosen_city

            def on_progress(done: int, total: int, label: str) -> None:
                self.detail = f"{label} ({done}/{total})" if total else label
                if total and done >= total:
                    self.completed = len(PHASES) - 1

            self.result, self.review = review.check_plan(
                self.result, chosen_city(self.result, self.cities), self.travel_dates,
                halal=self.halal, on_progress=on_progress,
            )
            self.checks = review.legacy_checks(self.review)
            self.detail = ""
            self.completed = len(PHASES)
            self.status = "done"
        except Exception as exc:  # reported to the client, not raised
            self.error = _friendly(exc, "plan")
            self.status = "error"

    def start(self) -> PlanJob:
        threading.Thread(target=self.run, daemon=True, name=f"plan-{self.id}").start()
        return self


@dataclass
class CheckJob:
    """Check an itinerary the traveller pasted. The text itself is not kept:
    only the report is stored and shared."""

    text: str
    start_date: date | None = None
    halal: bool = False
    destination: str = ""
    id: str = field(default_factory=_new_id)
    status: str = "queued"  # queued | running | done | error
    done: int = 0
    total: int = 0
    label: str = "Reading the itinerary"
    report: dict | None = None
    error: str = ""
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": "check",
            "status": self.status,
            "done": self.done,
            "total": self.total,
            "label": self.label,
            "report": self.report,
            "error": self.error,
            "created": self.created,
        }

    def run(self) -> None:
        from voyagent import review

        def on_progress(done: int, total: int, label: str) -> None:
            self.done, self.total, self.label = done, total, label

        self.status = "running"
        try:
            self.report = review.run(
                self.text, self.start_date, self.halal, self.destination, on_progress
            )
            self.text = ""  # not needed any more, and not ours to keep
            self.status = "done"
        except review.ReviewError as exc:
            self.error, self.status = str(exc), "error"
        except Exception as exc:  # reported to the client, not raised
            self.error = _friendly(exc, "check")
            self.status = "error"

    def start(self) -> CheckJob:
        threading.Thread(target=self.run, daemon=True, name=f"check-{self.id}").start()
        return self
