# To know more about the Task class, visit: https://docs.crewai.com/concepts/tasks
from crewai import Task
from textwrap import dedent


class TravelTasks:
    def __tip_section(self):
        return "If you do your BEST WORK, I'll give you a $10,000 commission!"

    def plan_itinerary(self, agent, city, travel_dates, interests):
        return Task(
            description=dedent(
                f"""
            ***Task**: Develop a 7-day travel itinerary for the chosen city.*
            **Description**: Expand the city guide into a full 7-day travel itinerary with detailed per-day plans, including weather forecasts, places to eat, packing suggestions, and a budget breakdown.
            You MUST suggest actual places to visit, actual hotels to stay, and actual restaurants to go to.
            This itinerary should cover all aspects of the trip, from arrival to departure, integrating the city guide information with practical travel logistics.
            Your final answer MUST be a complete expanded travel plan, formatted as markdown, encompassing a daily schedule, anticipated weather conditions, recommended clothing and items to pack, and a detailed budget, ensuring THE BEST TRIP EVER.
            Be specific and give it a reason why you picked each place, what makes them special!
            **Parameters**:
            - City: {city}
            - Travel Dates: {travel_dates}
            - Interests: {interests}

            **Note**: {self.__tip_section()}
    
            Make sure to use the most recent data as possible, and consider the current travel restrictions or requirements.
        """
            ),
            expected_output="Your final answer MUST be a complete expanded travel plan, formatted as markdown, encompassing a daily schedule, anticipated weather conditions, recommended clothing and items to pack, and a detailed budget, ensuring THE BEST TRIP EVER.",
            agent=agent,
        )


    def identify_city(self, agent,origin, destination, travel_dates, interests):
        return Task(
            description=dedent(
                f"""
            ***Task**: Identify the city for the travel itinerary.*
            **Description**: Analyze and select the most suitable city for a 7-day travel itinerary based on specific
            criteria such as weather patterns, seasonal events, and travel costs.
            This task involves comparing multiple cities considering factors like current weather conditions,upcoming events,and overall travel costs.
            **Parameters**:
            - Origin: {origin}
            - Cities: {destination}
            - Travel Date: {travel_dates}
            - Interests: {interests} 

           **Note**:{self.__tip_section()}

        """
            ),
            expected_output="Detailed report on the chosen city including flight costs, weather forecast, and attractions",
            agent=agent
        )
    
    def gather_city_info(self, agent,city, travel_date, interests):
        return Task(
            description=dedent(
                f"""
                ***Task**: Gather In-Depth City Information.
                **Description**: Compile an in-depth guide for the selected city, focusing on key attractions, local customs, special events, and daily activity recommendations.
                The guide should provide a thorough overview of what the city has to offer, including hidden gems, cultural hotspots, must-visit landmarks, weather forecasts, and high-level costs.
                This guide should be tailored to enhance the travel experience, providing practical tips and cultural insights.
                This guide should be know the must-visit landmarks, hidden gems, cultural hotspots, and practical travel tips.
                The final answer must be a comprehensive city guide.
                **Parameters**:
                - Cities: {city}
                - Travel Date: {travel_date}
                - Interests: {interests} 
                **Note**:{self.__tip_section()} """),
            expected_output="A detailed city guide including attractions, local customs, events, and daily activities",
            agent=agent
            )
