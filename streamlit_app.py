"""Streamlit web UI for Voyagent.

Run with:  streamlit run streamlit_app.py

Wraps the CrewAI ``TripCrew`` in a travel-themed web form. While the crew runs it
shows friendly, abstracted progress (never the agents' raw reasoning), then
renders the final markdown itinerary with a download button.
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

st.set_page_config(page_title="Voyagent · AI Travel Planner", page_icon="✈️", layout="centered")

# Tropical Sunset palette.
_SUNSET = "linear-gradient(120deg,#ff7a3d 0%,#ff3d77 42%,#d23bdb 72%,#7c3cff 100%)"


# --- Styling ------------------------------------------------------------------
# Supplementary polish for Streamlit's own elements. If the host sanitizes the
# <style> tag, the app still looks themed via .streamlit/config.toml, and the
# hero/result below use inline styles that always render.

_STYLE = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700;800&family=Poppins:wght@300;400;500;600&display=swap');
html, body, [class*="css"] {{ font-family: 'Poppins', sans-serif; }}
[data-testid="stAppViewContainer"] {{
    background:
        radial-gradient(1100px 480px at 12% -8%, #ffd9b0 0%, rgba(255,217,176,0) 60%),
        radial-gradient(1000px 520px at 92% -4%, #ffc6e0 0%, rgba(255,198,224,0) 58%),
        radial-gradient(900px 520px at 60% 110%, #e0d2ff 0%, rgba(224,210,255,0) 60%),
        linear-gradient(180deg, #fff5ef 0%, #fdf8ff 100%);
}}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ max-width: 780px; padding-top: 1.6rem; }}
[data-testid="stForm"] {{
    background: #ffffff; border: 1px solid #ffe1d6; border-radius: 22px;
    box-shadow: 0 20px 50px -28px rgba(210,59,119,.45);
}}
.stTextInput input, .stDateInput input {{ border-radius: 12px !important; }}
[data-testid="stFormSubmitButton"] button {{
    width: 100%; border: none; border-radius: 999px; padding: .75rem 1rem;
    font-weight: 600; font-size: 1.05rem; color: #fff; letter-spacing: .2px;
    background: {_SUNSET};
    box-shadow: 0 12px 26px -10px rgba(210,59,119,.7);
    transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
}}
[data-testid="stFormSubmitButton"] button:hover {{
    color:#fff; transform: translateY(-1px); filter: brightness(1.05);
    box-shadow: 0 16px 30px -10px rgba(210,59,119,.8);
}}
[data-testid="stProgress"] div[role="progressbar"] > div {{ background: {_SUNSET} !important; }}
</style>
"""
st.html(_STYLE)

# Hero — inline styles so it renders regardless of <style> sanitization.
st.html(
    f'<div style="border-radius:26px;padding:2.8rem 2rem 3rem;text-align:center;'
    f'color:#fff;margin-bottom:.4rem;background:{_SUNSET};'
    'box-shadow:0 22px 55px -22px rgba(210,59,119,.6);position:relative;overflow:hidden;">'
    '<div style="position:absolute;inset:0;background:radial-gradient(620px 220px at 78% -25%,'
    'rgba(255,255,255,.4),transparent 60%);"></div>'
    '<span style="position:relative;display:inline-block;font-size:.78rem;letter-spacing:.16em;'
    'text-transform:uppercase;background:rgba(255,255,255,.2);'
    'border:1px solid rgba(255,255,255,.45);padding:.36rem .95rem;border-radius:999px;">'
    '✈️ AI Travel Planner</span>'
    "<h1 style=\"position:relative;font-family:'Playfair Display',serif;font-size:3.4rem;"
    'line-height:1.04;margin:.7rem 0 .55rem;font-weight:800;color:#fff;'
    'text-shadow:0 2px 18px rgba(124,60,255,.35);">Voyagent</h1>'
    '<p style="position:relative;max-width:31rem;margin:0 auto;font-size:1.05rem;'
    'font-weight:300;opacity:.97;line-height:1.55;color:#fff;">Tell us where you dream of '
    'going. Our AI travel crew picks the perfect city, uncovers local secrets, and crafts '
    'your day-by-day itinerary.</p>'
    "</div>"
)
# Gradient divider beneath the hero.
st.html(
    f'<div style="height:5px;border-radius:999px;margin:.2rem 0 1.2rem;'
    f'background:{_SUNSET};opacity:.85;"></div>'
)


# --- Progress phases ----------------------------------------------------------

_PHASES = [
    ("✈️", "Choosing your destination"),
    ("🗺️", "Researching the city"),
    ("🧳", "Crafting your itinerary"),
]
# Generic, content-free heartbeat lines so the user sees motion without ever
# seeing the agents' raw reasoning.
_TICKERS = [
    "Scanning seasons and routes…",
    "Comparing destinations…",
    "Reading local guides…",
    "Hunting for hidden gems…",
    "Checking the weather…",
    "Pricing flights and stays…",
    "Penciling in your days…",
]


def _run_crew(crew: TripCrew, events: "queue.Queue", holder: dict) -> None:
    """Worker thread: run the crew, pushing abstracted progress signals.

    Only the queue and ``holder`` are touched here (never Streamlit APIs), and
    only sentinels are sent — never the agents' text.
    """

    def step_callback(_step=None) -> None:
        events.put("tick")  # content-free heartbeat

    def task_callback(_task=None) -> None:
        events.put("task_done")  # one phase finished

    try:
        result = crew.run(step_callback=step_callback, task_callback=task_callback)
        holder["result"] = getattr(result, "raw", None) or str(result)
    except Exception as exc:  # surfaced to the user in the main thread
        holder["error"] = exc
    finally:
        events.put(None)  # sentinel: worker finished


# --- App ----------------------------------------------------------------------

# Fail fast with a readable message if API keys are missing.
try:
    validate_env()
except MissingConfigError as exc:
    st.error(str(exc))
    st.stop()

_today = date.today()
with st.form("trip_form"):
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("🛫 Where from?", placeholder="Tunis")
    with col2:
        cities = st.text_input(
            "🌍 Candidate destinations", placeholder="Lisbon, Porto, Barcelona"
        )
    date_range = st.date_input(
        "📅 When are you travelling?",
        value=(_today, _today + timedelta(days=7)),
        min_value=_today,
        format="DD/MM/YYYY",
    )
    interests = st.text_input("💛 What do you love?", placeholder="food, architecture, beach")
    submitted = st.form_submit_button("Plan my trip ✨")

if submitted:
    # A date_input range returns a tuple; it has only one item until the second
    # date is chosen, so require both before continuing.
    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        st.warning("Please pick both a start and end date.")
        st.stop()
    if not all([origin.strip(), cities.strip(), interests.strip()]):
        st.warning("Please fill in where from, destinations, and what you love.")
        st.stop()

    start_date, end_date = date_range
    travel_dates = f"{start_date:%d %B %Y} - {end_date:%d %B %Y}"

    crew = TripCrew(origin, cities, travel_dates, interests)
    events: "queue.Queue" = queue.Queue()
    holder: dict = {}

    worker = threading.Thread(target=_run_crew, args=(crew, events, holder), daemon=True)
    worker.start()

    completed = 0
    tick = 0
    with st.status(
        f"{_PHASES[0][0]}  {_PHASES[0][1]}…", expanded=True
    ) as status:
        bar = st.progress(6)
        note = st.empty()
        done = False
        while not done:
            try:
                event = events.get(timeout=0.3)
            except queue.Empty:
                continue
            if event is None:
                done = True
            elif event == "task_done":
                completed = min(completed + 1, len(_PHASES))
                phase = min(completed, len(_PHASES) - 1)
                status.update(label=f"{_PHASES[phase][0]}  {_PHASES[phase][1]}…")
                bar.progress(int(completed / len(_PHASES) * 100))
            else:  # "tick" heartbeat
                tick += 1
                note.caption(_TICKERS[tick % len(_TICKERS)])

        if holder.get("error") is not None:
            status.update(label="Trip planning hit a snag.", state="error")
        else:
            bar.progress(100)
            status.update(label="Your trip plan is ready! 🎉", state="complete")

    if holder.get("error") is not None:
        st.error(f"Something went wrong while planning your trip:\n\n{holder['error']}")
    else:
        plan = holder.get("result", "")
        st.html(
            f'<div style="border-radius:18px 18px 0 0;padding:.85rem 1.3rem;color:#fff;'
            f'font-weight:600;font-size:1.15rem;background:{_SUNSET};margin-top:1.4rem;">'
            "🧳  Your itinerary</div>"
        )
        with st.container(border=True):
            st.markdown(plan)
        st.download_button(
            "⬇️  Download plan (Markdown)",
            data=plan,
            file_name="voyagent-trip-plan.md",
            mime="text/markdown",
        )

st.caption("Crafted by Voyagent · powered by an AI travel crew")
