from crewai import Agent
from langchain_openai import ChatOpenAI


from tools.search_tools import SearchTools
from tools.calculator_tools import CalculatorTool


from dotenv import load_dotenv
import os 
load_dotenv()


class TravelAgents():

  def city_selection_agent(self):
    return Agent(
        role='City Selection Expert',
        goal='Select the best city based on weather, season, and prices',
        backstory=
        'An expert in analyzing travel data to pick ideal destinations',
        tools=[SearchTools.search_internet,CalculatorTool.calculate],
        llm=ChatOpenAI(
          model='o1-mini',
          temperature=0.2),
        verbose=True)

  def local_expert(self):
    return Agent(
        role='Local Expert at this city',
        goal='Provide the BEST insights about the selected city',
        backstory="""A knowledgeable local guide with extensive information
        about the city, it's attractions and customs""",
        tools=[
            SearchTools.search_internet
            ],
        verbose=True)

  def travel_concierge(self):
    return Agent(
        role='Amazing Travel Concierge',
        goal="""Create the most amazing travel itineraries with budget and 
        packing suggestions for the city""",
        backstory="""Specialist in travel planning and logistics with 
        decades of experience""",
        tools=[
            SearchTools.search_internet,
            CalculatorTool.calculate,
        ],
        verbose=True)