# Trip Planner Agent

## Overview

The Trip Planner Agent is an AI-powered travel planning tool built with the crewai framework. It uses specialized AI agents to generate detailed travel itineraries, city information, and logistical support based on user preferences.

## Features

• Intelligent City Selection: AI-driven city recommendations based on weather, season, and pricing.

• Local Insights: In-depth information on attractions, customs, and events for selected cities.

• Comprehensive Itineraries: Detailed 7-day travel plans including daily schedules, weather, packing, and budget.

• Modular AI Agents: Flexible architecture using crewai for scalable travel planning.

• Tool Integration: Utilizes internet search and calculator tools for real-time data.

## To get started with the Trip Planner Agent:

 1. Clone the repository

 2.Install dependencies (Poetry recommended)

 3.Configure API Keys: Create a .env file and add your necessary API keys (e.g., OPENAI_API_KEY).

 4.Run the application

## Project Structure

• main.py: Application entry point and crew orchestration.

• agents.py: Defines AI agents (City Selection Expert, Local Expert, Travel Concierge).

• tasks.py: Defines tasks for agents (Plan Itinerary, Identify City, Gather City Info).

• tools/: Contains utility tools (calculator_tools.py, search_tools.py).
