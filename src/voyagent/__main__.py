"""CLI entry point for the Voyagent.

Run with:  python -m voyagent   (or the ``voyagent`` console script)
"""

import sys
from textwrap import dedent

from voyagent.config import MissingConfigError, validate_env
from voyagent.crew import TripCrew


def _force_utf8_stdout() -> None:
    """Avoid Windows ``cp1252`` UnicodeEncodeError when CrewAI logs emoji.

    CrewAI's verbose output includes characters (e.g. the rocket emoji) that the
    default Windows console encoding cannot represent. Reconfiguring to UTF-8
    keeps the run from spamming codec errors.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main() -> None:
    _force_utf8_stdout()
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
