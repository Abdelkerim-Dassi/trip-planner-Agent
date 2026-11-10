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
    summary = (plan.get("review") or {}).get("summary") or {}
    if summary.get("places"):
        # Say exactly what was checked, never "every place".
        counts = f"{summary['confirmed'] + summary.get('far', 0)} of {summary['places']} places found on the map"
        if summary.get("hours_checked"):
            counts += f", opening days checked for {summary['hours_checked']} sights"
    else:
        counts = ""
    prompt = dedent(
        f"""
        You write short social posts for ReelTrip, a free tool that checks trip
        plans against the real world (is each place on the map, is it open on
        the day you go) and builds plans from places people save on TikTok.

        Write a post sharing this trip plan to {city} ({req.get('travel_dates', '')},
        for someone who loves {req.get('interests', 'travel')}).
        What was checked (use these numbers as they are, never say "every
        place" or "all places"): {counts or 'the places were looked up on OpenStreetMap'}.
        {'; '.join(checked)}

        Rules:
        - Use only places and facts that appear in the plan below.
        - "hook": max 12 words, the first line people see; specific, no clickbait.
        - "caption": 3-5 short lines with 2-4 emojis, a real highlight from the
          plan, and end with "Check yours free: {PUBLIC_URL}".
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
