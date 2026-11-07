"""Content Writer: turns a finished plan into a ready-to-post social caption.

Runs on the helper model (free Gemini when configured, see
``config.helper_model``) so it never touches the main model's budget, and
only when someone opens the "Post this trip" page.
"""

from __future__ import annotations

import logging
from textwrap import dedent

from voyagent.hours import chosen_city
from voyagent.llm import complete_json

log = logging.getLogger(__name__)

PUBLIC_URL = "reeltrip.onrender.com"


def social_post(plan: dict) -> dict:
    """``{"hook", "caption", "hashtags", "script"}``; ``{}`` if the model fails."""
    req = plan.get("request", {})
    city = chosen_city(plan.get("result", ""), req.get("cities", "")) or req.get("cities", "")
    checked = [
        f"{c['name']} ({'moved off a closed day' if c.get('status') == 'moved' else 'opening days checked'})"
        for c in plan.get("checks", []) if c.get("status") in ("ok", "moved")
    ]
    prompt = dedent(
        f"""
        You write short social posts for ReelTrip, a free trip planner that turns
        places people save on TikTok into a day-by-day plan, checking every
        place on OpenStreetMap and its opening days.

        Write a post sharing this trip plan to {city} ({req.get('travel_dates', '')},
        for someone who loves {req.get('interests', 'travel')}).
        Facts we checked: {'; '.join(checked) or 'every place is on the map'}.

        Rules:
        - Use only places and facts that appear in the plan below.
        - "hook": max 12 words, the first line people see; specific, no clickbait.
        - "caption": 3-5 short lines with 2-4 emojis, a real highlight from the
          plan, and end with "Plan yours free: {PUBLIC_URL}".
        - "hashtags": 6-8 relevant tags without the # sign (destination, region,
          travel style).
        - "script": a 20-second voice-over for a slideshow video, 45-60 words.
        - Write in English.

        Return JSON only: {{"hook": "...", "caption": "...", "hashtags": ["..."], "script": "..."}}

        Plan:
        {plan.get('result', '')[:4500]}
        """
    ).strip()
    try:
        data = complete_json(prompt, max_tokens=3000)
    except Exception as exc:
        log.warning("Social post failed: %s", exc)
        return {}
    if not data.get("caption"):
        return {}
    tags = [str(t).lstrip("#").replace(" ", "") for t in data.get("hashtags") or [] if str(t).strip()]
    return {
        "hook": str(data.get("hook", "")).strip(),
        "caption": str(data.get("caption", "")).strip(),
        "hashtags": tags[:8],
        "script": str(data.get("script", "")).strip(),
    }
