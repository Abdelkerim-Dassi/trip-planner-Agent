"""Plan exports that need no account: an .ics calendar of the trip days."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from voyagent.plan_text import split_days, strip_markdown


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding: at most 75 octets per line."""
    out, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > 73:
            out.append(current.decode("utf-8"))
            current = b""
        current += encoded
    out.append(current.decode("utf-8"))
    return "\r\n ".join(out)


def to_ics(plan: dict, url: str = "") -> str:
    """One all-day event per dated trip day, with that day's schedule."""
    req = plan.get("request", {})
    days = [d for d in split_days(plan.get("result", ""), req.get("travel_dates", "")) if d.date]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TripCorrect//Trip plan//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape('TripCorrect: ' + req.get('cities', 'trip'))}",
    ]
    for day in days:
        schedule = "\n".join(day.items) if day.items else strip_markdown(day.text)
        if url:
            schedule += f"\n\nFull plan: {url}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{plan.get('id', 'plan')}-day{day.number}@tripcorrect",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day.date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{day.date + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(day.heading)}",
            f"DESCRIPTION:{_escape(schedule)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
