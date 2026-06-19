"""Streamlit web UI for Voyagent.

Run with:  streamlit run streamlit_app.py

Wraps the CrewAI ``TripCrew`` in a travel-themed web form, streams live agent
progress while the crew runs, then renders the final markdown itinerary with a
download button.
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


# --- Styling ------------------------------------------------------------------

_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Poppins:wght@300;400;500;600&display=swap');

/* Warm travel-sky backdrop */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(1200px 500px at 20% -10%, #ffe3c7 0%, rgba(255,227,199,0) 60%),
        radial-gradient(1000px 500px at 90% 0%, #cdeefb 0%, rgba(205,238,251,0) 55%),
        linear-gradient(180deg, #fef7f0 0%, #fdfbf7 100%);
    font-family: 'Poppins', sans-serif;
}
[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 760px; padding-top: 2rem; }

/* Hero */
.hero {
    border-radius: 24px;
    padding: 2.6rem 2rem 2.9rem;
    background: linear-gradient(120deg, #ff9966 0%, #ff7a59 38%, #ef5d8f 72%, #7c5cff 100%);
    box-shadow: 0 18px 40px -18px rgba(239, 93, 143, 0.55);
    text-align: center;
    color: #fff;
    position: relative;
    overflow: hidden;
}
.hero::after {
    content: "";
    position: absolute; inset: 0;
    background: radial-gradient(600px 220px at 80% -20%, rgba(255,255,255,.35), transparent 60%);
}
.hero .badge {
    display: inline-block;
    font-size: .8rem; letter-spacing: .14em; text-transform: uppercase;
    font-weight: 500;
    background: rgba(255,255,255,.18);
    border: 1px solid rgba(255,255,255,.35);
    padding: .35rem .9rem; border-radius: 999px;
    backdrop-filter: blur(4px);
}
.hero h1 {
    font-family: 'Playfair Display', serif;
    font-size: 3.3rem; line-height: 1.05; margin: .7rem 0 .5rem;
    font-weight: 700; letter-spacing: -.5px;
}
.hero p {
    max-width: 30rem; margin: 0 auto; font-size: 1.02rem;
    font-weight: 300; opacity: .96; line-height: 1.5;
}

/* Form card */
[data-testid="stForm"] {
    background: #ffffff;
    border: 1px solid #f1e6da;
    border-radius: 20px;
    padding: 1.6rem 1.6rem .4rem;
    box-shadow: 0 14px 40px -24px rgba(60,40,20,.35);
    margin-top: -1.6rem;
}

/* Inputs */
[data-testid="stForm"] label p { font-weight: 500 !important; color: #4a3a2c; }
.stTextInput input, .stDateInput input {
    border-radius: 12px !important;
}

/* Submit button */
[data-testid="stFormSubmitButton"] button {
    width: 100%;
    border: none;
    border-radius: 999px;
    padding: .7rem 1rem;
    font-weight: 600; font-size: 1.02rem;
    color: #fff;
    background: linear-gradient(120deg, #ff7a59 0%, #ef5d8f 60%, #7c5cff 100%);
    box-shadow: 0 10px 22px -10px rgba(239,93,143,.7);
    transition: transform .12s ease, box-shadow .12s ease;
}
[data-testid="stFormSubmitButton"] button:hover {
    transform: translateY(-1px);
    box-shadow: 0 14px 26px -10px rgba(239,93,143,.8);
    color: #fff;
}

/* Itinerary result card */
.plan-card {
    background: #fff;
    border: 1px solid #f1e6da;
    border-radius: 20px;
    padding: .4rem 1.8rem 1rem;
    box-shadow: 0 14px 40px -24px rgba(60,40,20,.35);
}
.section-title {
    font-family: 'Playfair Display', serif;
    font-size: 1.7rem; color: #23303d; margin: 1.6rem 0 .2rem;
}
.foot { text-align:center; color:#9a8a7a; font-size:.82rem; margin: 2rem 0 .5rem; }
</style>
"""
st.markdown(_STYLE, unsafe_allow_html=True)

st.markdown(
    """
    <div class="hero">
        <span class="badge">✈️ AI Travel Planner</span>
        <h1>Voyagent</h1>
        <p>Tell us where you dream of going. Our AI travel crew picks the perfect
        city, uncovers local secrets, and crafts your day-by-day itinerary.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# --- Helpers ------------------------------------------------------------------


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
        events.put(f"🧭 {_describe(step)}")

    def task_callback(task) -> None:
        events.put(f"✅ Step complete — {_describe(task)}")

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

    log_lines: list[str] = []
    with st.status(
        "Your travel crew is on it… this can take a few minutes.", expanded=True
    ) as status:
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
            status.update(label="Trip planning hit a snag.", state="error")
        else:
            status.update(label="Your trip plan is ready! 🎉", state="complete")

    if holder.get("error") is not None:
        st.error(f"Something went wrong while planning your trip:\n\n{holder['error']}")
    else:
        plan = holder.get("result", "")
        st.markdown('<div class="section-title">🧳 Your itinerary</div>', unsafe_allow_html=True)
        st.markdown('<div class="plan-card">', unsafe_allow_html=True)
        st.markdown(plan)
        st.markdown("</div>", unsafe_allow_html=True)
        st.download_button(
            "⬇️  Download plan (Markdown)",
            data=plan,
            file_name="voyagent-trip-plan.md",
            mime="text/markdown",
        )

st.markdown('<div class="foot">Crafted by Voyagent · powered by an AI travel crew</div>',
            unsafe_allow_html=True)
