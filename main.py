import os
from crewai import Crew
from textwrap import dedent
from agents import TravelAgents
from tasks import TravelTasks


class TripCrew:
    def __init__(self, origin, cities,date_range,interests):
        self.origin = origin
        self.cities = cities
        self.date_range = date_range
        self.interests = interests

    def run(self):
        # Define your custom agents and tasks in agents.py and tasks.py
        agents = TravelAgents()
        tasks = TravelTasks()

        # Define your custom agents and tasks here
        expert_travel_agent = agents.city_selection_agent()
        city_selection_expert = agents.local_expert()
        local_tour_guide = agents.travel_concierge()

        # Custom tasks include agent name and variables as input
        plan_itinerary = tasks.plan_itinerary(
            expert_travel_agent,
            self.cities,
            self.date_range,
            self.interests
        )

        identify_city = tasks.identify_city(
            city_selection_expert,
            self.origin,
            self.cities,
            self.date_range,
            self.interests
        )
        gather_city_info = tasks.gather_city_info(
            local_tour_guide,
            self.cities,
            self.date_range,
            self.interests
        )

        # Define your custom crew here
        crew = Crew(
            agents=[expert_travel_agent, local_tour_guide, city_selection_expert],
            tasks=[plan_itinerary, identify_city, gather_city_info],
            verbose=True,
        )

        result = crew.kickoff()
        return result


# This is the main function that you will use to run your custom crew.
if __name__ == "__main__":
    print("## Welcome to you AI Travel Crew!")
    print("-------------------------------")
    origin = input(dedent("""Enter origin: """))
    destination = input(dedent("""Enter destination: """))
    travel_dates = input(dedent("""Enter travel time range: """))
    interests = input(dedent("""Enter interests: """))

    Travel_crew = TripCrew(origin, destination, travel_dates, interests)
    result = Travel_crew.run()
    print("\n\n########################")
    print("## Here is you Trip plann:")
    print("########################\n")
    print(result)
