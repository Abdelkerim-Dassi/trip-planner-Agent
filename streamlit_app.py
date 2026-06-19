"""Streamlit web UI for the Voyagent.

Run with:  streamlit run streamlit_app.py

Wraps the existing CrewAI ``TripCrew`` in a web form, streams live agent
progress while the crew runs (~1-3 minutes), then renders the final markdown
trip plan with a download button.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

# On Streamlit Community Cloud, API keys are set in the dashboard and exposed via
# st.secrets. voyagent.config reads os.environ at import time, so copy any secrets
# into the environment first. No-op locally (no secrets file), where the .env is
# loaded by config instead. setdefault means a real env var always wins.
try:
    for _key, _value in st.secrets.items():
        os.environ.setdefault(_key, str(_value))
except Exception:
    pass

# Make the src-layout package importable even when it isn't pip-installed
# (e.g. running `streamlit run streamlit_app.py` straight from a clone).
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from voyagent.config import MissingConfigError, validate_env
from voyagent.crew import TripCrew

st.set_page_config(page_title="Voyagent", page_icon="🧳", layout="centered")


def _describe(obj) -> str:
    """Turn a CrewAI step/task callback payload into a short readable line."""
    for attr in ("raw", "output", "result", "description"):
        value = getattr(obj, attr, None)
        if value:
            text = str(value).strip().replace("\n", " ")
            return text[:240] + ("…" if len(text) > 240 else "")
    text = str(obj).strip().replace("\n", " ")
    return text[:240] + ("…" if len(text) > 240 else "")


def _run_crew(crew: TripCrew, events: "queue.Queue", holder: dict) -> None:
    """Worker thread: run the crew, pushing progress lines onto ``events``.

    Only the queue and ``holder`` are touched here (never Streamlit APIs), so no
    Streamlit script context is needed in this thread.
    """

    def step_callback(step) -> None:
        events.put(f"🔧 {_describe(step)}")

    def task_callback(task) -> None:
        events.put(f"✅ Task complete — {_describe(task)}")

    try:
        result = crew.run(step_callback=step_callback, task_callback=task_callback)
        holder["result"] = getattr(result, "raw", None) or str(result)
    except Exception as exc:  # surfaced to the user in the main thread
        holder["error"] = exc
    finally:
        events.put(None)  # sentinel: worker finished


st.title("🧳 Voyagent")
st.caption("A CrewAI travel crew picks your city, researches it, and builds a full itinerary.")

# Fail fast with a readable message if API keys are missing.
try:
    validate_env()
except MissingConfigError as exc:
    st.error(str(exc))
    st.stop()

_today = date.today()
with st.form("trip_form"):
    origin = st.text_input("Origin", placeholder="Tunis")
    cities = st.text_input(
        "Candidate destinations (comma-separated)", placeholder="Lisbon, Porto, Barcelona"
    )
    date_range = st.date_input(
        "Travel dates",
        value=(_today, _today + timedelta(days=7)),
        min_value=_today,
        format="DD/MM/YYYY",
    )
    interests = st.text_input("Interests", placeholder="food, architecture, beach")
    submitted = st.form_submit_button("Plan my trip ✨")

if submitted:
    # A date_input range returns a tuple; it has only one item until the second
    # date is chosen, so require both before continuing.
    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        st.warning("Please pick both a start and end date.")
        st.stop()
    if not all([origin.strip(), cities.strip(), interests.strip()]):
        st.warning("Please fill in origin, destinations, and interests.")
        st.stop()

    start_date, end_date = date_range
    travel_dates = f"{start_date:%d %B %Y} - {end_date:%d %B %Y}"

    crew = TripCrew(origin, cities, travel_dates, interests)
    events: "queue.Queue" = queue.Queue()
    holder: dict = {}

    worker = threading.Thread(target=_run_crew, args=(crew, events, holder), daemon=True)
    worker.start()

    log_lines: list[str] = []
    with st.status("Planning your trip… this can take 1-3 minutes.", expanded=True) as status:
        log_area = st.empty()
        done = False
        while not done:
            try:
                event = events.get(timeout=0.2)
            except queue.Empty:
                continue
            if event is None:
                done = True
            else:
                log_lines.append(event)
                log_area.markdown("\n\n".join(log_lines[-12:]))

        if holder.get("error") is not None:
            status.update(label="Trip planning failed.", state="error")
        else:
            status.update(label="Trip plan ready!", state="complete")

    if holder.get("error") is not None:
        st.error(f"Something went wrong while planning your trip:\n\n{holder['error']}")
    else:
        plan = holder.get("result", "")
        st.subheader("Your trip plan")
        st.markdown(plan)
        st.download_button(
            "Download plan (Markdown)",
            data=plan,
            file_name="trip-plan.md",
            mime="text/markdown",
        )
