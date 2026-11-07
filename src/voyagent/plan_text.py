"""Read the structure of a finished markdown plan: its days and their items.

Plans are markdown written by a model, so this is deliberately forgiving: a
day starts at any heading containing "Day N", and its items are table rows or
bullet points. Used by the opening-hours check, the calendar export and the
share images.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from voyagent.travel_info import parse_date_range

# "## Day 1: Monday 07 December 2026", or a bold line "**Day 1 - Monday**".
_DAY_HEADING = re.compile(
    r"^(?:#{1,4}\s*\**|\*\*)\s*Day\s+(\d+)\b[^\n]*$", re.IGNORECASE | re.MULTILINE
)
_TABLE_DIVIDER = re.compile(r"^\s*\|?\s*:?-{2,}")


@dataclass
class Day:
    number: int
    heading: str
    text: str
    date: date | None = None
    items: list[str] = field(default_factory=list)

    @property
    def weekday(self) -> str:
        return f"{self.date:%A}" if self.date else ""


def strip_markdown(text: str) -> str:
    """Plain text: no links, emphasis, heading marks or HTML tags."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)
    return re.sub(r"[ \t]+", " ", text).strip()


def _items(text: str) -> list[str]:
    """One line per scheduled item: "Morning: Bardo Museum ..." from a table
    row, or the text of a bullet point."""
    items: list[str] = []
    header_skipped = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            if _TABLE_DIVIDER.match(line):
                continue
            cells = [strip_markdown(c) for c in line.strip("|").split("|")]
            cells = [c for c in cells if c]
            if not header_skipped and cells and cells[0].lower() in {"time", "when", "slot", "part of day"}:
                header_skipped = True
                continue
            if len(cells) >= 2:
                items.append(f"{cells[0]}: {cells[1]}")
            elif cells:
                items.append(cells[0])
        elif re.match(r"^[-*+]\s+|^\d+\.\s+", line):
            items.append(strip_markdown(re.sub(r"^[-*+]\s+|^\d+\.\s+", "", line)))
    return [i for i in items if i]


def split_days(markdown: str, travel_dates: str = "") -> list[Day]:
    """The plan's day sections, in order, dated when the trip dates parse."""
    parsed = parse_date_range(travel_dates) if travel_dates else None
    matches = list(_DAY_HEADING.finditer(markdown))
    days: list[Day] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end]
        if index + 1 == len(matches):
            # The last day ends at the next heading of the same or a higher
            # level (Weather, Budget...); its own sub-headings stay inside.
            level = len(match.group(0)) - len(match.group(0).lstrip("#")) or 3
            nxt = re.search(rf"^#{{1,{level}}}\s", body, re.MULTILINE)
            if nxt:
                body = body[: nxt.start()]
        number = int(match.group(1))
        when = parsed[0] + timedelta(days=number - 1) if parsed else None
        if parsed and when > parsed[1]:
            when = None
        days.append(
            Day(
                number=number,
                heading=strip_markdown(match.group(0)),
                text=body.strip(),
                date=when,
                items=_items(body),
            )
        )
    return days
