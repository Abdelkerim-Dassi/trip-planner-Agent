"""Crew orchestration: wires the three agents to their tasks and runs them."""

from crewai import Crew

from trip_planner.agents import TravelAgents
from trip_planner.tasks import TravelTasks


class TripCrew:
    def __init__(self, origin, cities, date_range, interests):
        self.origin = origin
        self.cities = cities
        self.date_range = date_range
        self.interests = interests

    def run(self):
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

        # Tasks run in logical order: pick the city, learn about it, then plan.
        crew = Crew(
            agents=[city_selector, local_expert, concierge],
            tasks=[identify_city, gather_city_info, plan_itinerary],
            verbose=True,
        )

        return crew.kickoff()
