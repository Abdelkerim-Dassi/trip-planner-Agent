"""CLI entry point for the Trip Planner Agent.

Run with:  python -m trip_planner   (or the ``trip-planner`` console script)
"""

from textwrap import dedent

from trip_planner.config import MissingConfigError, validate_env
from trip_planner.crew import TripCrew


def main() -> None:
    try:
        validate_env()
    except MissingConfigError as exc:
        print(f"Configuration error:\n{exc}")
        raise SystemExit(1)

    print("## Welcome to your AI Travel Crew!")
    print("-------------------------------")
    origin = input(dedent("""Enter origin: """))
    cities = input(dedent("""Enter candidate destinations (comma-separated): """))
    travel_dates = input(dedent("""Enter travel time range: """))
    interests = input(dedent("""Enter interests: """))

    crew = TripCrew(origin, cities, travel_dates, interests)
    result = crew.run()

    print("\n\n########################")
    print("## Here is your Trip plan:")
    print("########################\n")
    print(result)


if __name__ == "__main__":
    main()
