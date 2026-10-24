"""Background plan jobs shared by the web app and the MCP server.

A crew run takes minutes, so callers start a :class:`PlanJob` in a thread and
poll it. Jobs only expose abstracted progress (which phase is running), never
the agents' raw reasoning.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

#: One phase per crew task, in run order (see voyagent.crew).
PHASES = [
    ("✈️", "Choosing your destination"),
    ("🗺️", "Researching the city"),
    ("✨", "Uncovering hidden gems"),
    ("🧳", "Crafting your itinerary"),
    ("🚇", "Sorting out the logistics"),
    ("🔍", "Refining every detail"),
    ("📖", "Polishing your plan"),
]


@dataclass
class PlanJob:
    origin: str
    cities: str
    travel_dates: str
    interests: str
    inspiration: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "queued"  # queued | running | done | error
    completed: int = 0
    steps: int = 0
    result: str = ""
    error: str = ""
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
            "completed": self.completed,
            "total": len(PHASES),
            "steps": self.steps,
            "result": self.result,
            "error": self.error,
            "request": {
                "origin": self.origin,
                "cities": self.cities,
                "travel_dates": self.travel_dates,
                "interests": self.interests,
            },
        }

    def run(self) -> None:
        """Run the crew to completion in the calling thread."""
        def step_callback(_step=None) -> None:
            self.steps += 1

        def task_callback(_task=None) -> None:
            self.completed = min(self.completed + 1, len(PHASES))

        self.status = "running"
        try:
            from voyagent.crew import TripCrew  # heavy import; only when planning

            crew = TripCrew(
                self.origin, self.cities, self.travel_dates, self.interests, self.inspiration
            )
            result = crew.run(step_callback=step_callback, task_callback=task_callback)
            self.result = getattr(result, "raw", None) or str(result)
            self.completed = len(PHASES)
            self.status = "done"
        except Exception as exc:  # reported to the client, not raised
            self.error = str(exc)
            self.status = "error"

    def start(self) -> PlanJob:
        threading.Thread(target=self.run, daemon=True, name=f"plan-{self.id}").start()
        return self
