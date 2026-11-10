"""Images that make a finished plan shareable.

- :func:`og_card`: the 1200x630 preview shown when a plan link is pasted into
  WhatsApp, Instagram DMs, X, Slack...
- :func:`slides`: a 1080x1350 carousel (cover, one slide per day, a map of
  the checked places, a closing slide) ready to post on Instagram or as a
  TikTok photo post. Every slide carries the ReelTrip address, so each shared
  plan brings the next traveller.

Drawn with Pillow; the map slide stitches OpenStreetMap tiles (low volume,
identified User-Agent, attribution on the image, per the tile usage policy).
"""

from __future__ import annotations

import io
import math
import os
from functools import lru_cache

import requests
from PIL import Image, ImageDraw, ImageFont

from voyagent.hours import chosen_city
from voyagent.places import USER_AGENT
from voyagent.plan_text import split_days, strip_markdown

PUBLIC_HOST = os.environ.get("VOYAGENT_PUBLIC_HOST", "reeltrip.onrender.com")
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
SLIDE_SIZE = (1080, 1350)
OG_SIZE = (1200, 630)
MAX_DAY_SLIDES = 10

_SUNSET = [(255, 122, 61), (255, 61, 119), (210, 59, 219), (124, 60, 255)]
_INK = (42, 31, 45)
_MUTED = (122, 107, 125)
_PINK = (255, 61, 119)
_GREEN = (31, 157, 107)

# Fonts with accents and dashes: DejaVu in the Docker image (fonts-dejavu-core),
# Segoe UI / Arial on Windows. Pillow's built-in font is the last resort.
_FONT_CANDIDATES = {
    "regular": [
        os.environ.get("VOYAGENT_FONT", ""),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ],
    "bold": [
        os.environ.get("VOYAGENT_FONT_BOLD", ""),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ],
}


@lru_cache(maxsize=64)
def _font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES[weight]:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


# --- Drawing helpers -------------------------------------------------------------


def _gradient(size: tuple[int, int]) -> Image.Image:
    """The site's sunset gradient, drawn diagonally."""
    w, h = size
    small = Image.new("RGB", (64, 64))
    px = small.load()
    stops = len(_SUNSET) - 1
    for y in range(64):
        for x in range(64):
            t = (x / 63 * 0.65 + y / 63 * 0.35) * stops
            i = min(int(t), stops - 1)
            f = t - i
            a, b = _SUNSET[i], _SUNSET[i + 1]
            px[x, y] = tuple(round(a[k] + (b[k] - a[k]) * f) for k in range(3))
    return small.resize((w, h), Image.BICUBIC)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    if line and len(lines) < max_lines:
        lines.append(line)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def _text_block(draw, xy, text, font, fill, width, max_lines, spacing=1.25) -> int:
    """Draw wrapped text; return the y below it."""
    x, y = xy
    size = getattr(font, "size", 20)
    for line in _wrap(draw, text, font, width, max_lines):
        draw.text((x, y), line, font=font, fill=fill)
        y += int(size * spacing)
    return y


def _footer(draw, size, color=(255, 255, 255)) -> None:
    w, h = size
    font = _font(30, "bold")
    label = f"Check yours free · {PUBLIC_HOST}"
    draw.text(((w - draw.textlength(label, font=font)) / 2, h - 80), label, font=font, fill=color)


def _png(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _title(plan: dict) -> str:
    req = plan.get("request", {})
    return chosen_city(plan.get("result", ""), req.get("cities", "")) or req.get("cities", "Your trip")


def _days(plan: dict):
    return split_days(plan.get("result", ""), plan.get("request", {}).get("travel_dates", ""))


# --- Link preview card -------------------------------------------------------------


def og_card(plan: dict) -> bytes:
    req = plan.get("request", {})
    days = _days(plan)
    image = _gradient(OG_SIZE)
    draw = ImageDraw.Draw(image)
    draw.text((70, 60), "ReelTrip", font=_font(34, "bold"), fill="white")
    draw.text((70, 104), "Trip plans, checked against the real world", font=_font(24), fill=(255, 235, 245))
    y = _text_block(draw, (70, 175), _title(plan), _font(92, "bold"), "white", 1060, 2, 1.1)
    sub = f"{len(days)}-day checked plan" if days else "Checked trip plan"
    if req.get("travel_dates"):
        sub += f" · {req['travel_dates']}"
    y = _text_block(draw, (70, y + 10), sub, _font(34), "white", 1060, 2)
    spots = [c["name"] for c in plan.get("checks", []) if c.get("on_map")][:3]
    x = 70
    for name in spots:
        font = _font(26, "bold")
        label = name
        width = draw.textlength(label, font=font) + 40
        if x + width > OG_SIZE[0] - 70:
            break
        draw.rounded_rectangle((x, y + 24, x + width, y + 74), radius=25, fill=(255, 255, 255))
        draw.text((x + 20, y + 33), label, font=font, fill=_PINK)
        x += width + 14
    draw.text((70, OG_SIZE[1] - 64), PUBLIC_HOST, font=_font(26), fill=(255, 235, 245))
    return _png(image)


def _verdict(summary: dict) -> str:
    problems, warnings = summary.get("problems", 0), summary.get("warnings", 0)
    if problems:
        return f"{problems} problem{'s' if problems != 1 else ''} found"
    if warnings:
        return f"{warnings} thing{'s' if warnings != 1 else ''} to double-check"
    return "No problems found"


def report_card(report: dict) -> bytes:
    """Link preview for a shared itinerary check: the verdict in one glance."""
    summary = report.get("summary", {})
    image = _gradient(OG_SIZE)
    draw = ImageDraw.Draw(image)
    draw.text((70, 60), "ReelTrip", font=_font(34, "bold"), fill="white")
    draw.text((70, 104), "Itinerary check", font=_font(24), fill=(255, 235, 245))
    title = report.get("destination") or "Trip plan"
    y = _text_block(draw, (70, 170), title, _font(76, "bold"), "white", 1060, 2, 1.1)
    y = _text_block(draw, (70, y + 14), _verdict(summary), _font(58, "bold"), "white", 1060, 1)
    found = summary.get("confirmed", 0) + summary.get("far", 0)
    sub = f"{found} of {summary.get('places', 0)} places found on the map"
    if summary.get("hours_checked"):
        sub += f" · opening days checked for {summary['hours_checked']}"
    _text_block(draw, (70, y + 16), sub, _font(30), (255, 235, 245), 1060, 2)
    draw.text((70, OG_SIZE[1] - 64), f"Check yours free · {PUBLIC_HOST}", font=_font(26), fill=(255, 235, 245))
    return _png(image)


@lru_cache(maxsize=1)
def home_card() -> bytes:
    """Link preview for the home page."""
    image = _gradient(OG_SIZE)
    draw = ImageDraw.Draw(image)
    draw.text((70, 60), "ReelTrip", font=_font(34, "bold"), fill="white")
    y = _text_block(
        draw, (70, 160), "Your AI planned your trip. We check it.", _font(80, "bold"), "white", 1060, 3, 1.1
    )
    _text_block(
        draw, (70, y + 24),
        "Each place looked up on the map. Closed days, wrong cities and impossible days flagged. "
        "Free, no account.",
        _font(32), (255, 235, 245), 1060, 3,
    )
    draw.text((70, OG_SIZE[1] - 64), PUBLIC_HOST, font=_font(26), fill=(255, 235, 245))
    return _png(image)


# --- Carousel slides -----------------------------------------------------------------


def _cover(plan: dict, count: int) -> Image.Image:
    req = plan.get("request", {})
    image = _gradient(SLIDE_SIZE)
    draw = ImageDraw.Draw(image)
    w, _ = SLIDE_SIZE
    draw.text((90, 110), "ReelTrip", font=_font(46, "bold"), fill="white")
    y = _text_block(draw, (90, 420), _title(plan), _font(130, "bold"), "white", w - 180, 3, 1.05)
    days = _days(plan)
    sub = f"{len(days)} days, planned and checked" if days else "A trip, planned and checked"
    y = _text_block(draw, (90, y + 30), sub, _font(52), "white", w - 180, 2)
    if req.get("travel_dates"):
        y = _text_block(draw, (90, y + 10), req["travel_dates"], _font(40), (255, 235, 245), w - 180, 2)
    draw.text((90, y + 60), f"Swipe for the plan → ({count} slides)", font=_font(36), fill="white")
    _footer(draw, SLIDE_SIZE)
    return image


def _day_slide(plan: dict, day) -> Image.Image:
    w, h = SLIDE_SIZE
    image = _gradient(SLIDE_SIZE)
    draw = ImageDraw.Draw(image)
    card = (60, 70, w - 60, h - 150)
    draw.rounded_rectangle(card, radius=48, fill="white")
    x0, width = card[0] + 60, card[2] - card[0] - 120
    title = f"Day {day.number}" + (f" · {day.date:%A %d %b}" if day.date else "")
    draw.text((x0, card[1] + 60), title, font=_font(64, "bold"), fill=_PINK)
    y = card[1] + 170
    items = day.items or [strip_markdown(day.text)]
    for item in items[:6]:
        if y > card[3] - 180:
            break
        label, _, rest = item.partition(": ")
        if rest and len(label) <= 16:
            draw.text((x0, y), label.upper(), font=_font(30, "bold"), fill=_MUTED)
            y += 44
            text = rest
        else:
            text = item
        # "Area | Activity" rows: the longest cell is the one that says what to do.
        y = _text_block(draw, (x0, y), max(text.split(" | "), key=len), _font(38), _INK, width, 3) + 26
    checked = [
        c["name"] for c in plan.get("checks", [])
        if day.number in (c.get("days") or []) and c.get("status") in ("ok", "moved")
    ]
    if checked:
        note = "Open that day: " + ", ".join(checked)
        _text_block(draw, (x0, card[3] - 120), note, _font(30, "bold"), _GREEN, width, 2)
    _footer(draw, SLIDE_SIZE)
    return image


def _deg2tile(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


@lru_cache(maxsize=256)
def _tile(z: int, x: int, y: int) -> Image.Image | None:
    try:
        response = requests.get(
            TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT}, timeout=10
        )
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except (requests.RequestException, OSError):
        return None


def _map(points: list[tuple[float, float]], size: tuple[int, int]) -> Image.Image | None:
    """A map of ``points`` (lat, lon) from OSM tiles, with numbered pins."""
    w, h = size
    lats, lons = [p[0] for p in points], [p[1] for p in points]
    zoom = 5
    for z in range(16, 4, -1):
        x1, y1 = _deg2tile(max(lats), min(lons), z)
        x2, y2 = _deg2tile(min(lats), max(lons), z)
        if (x2 - x1) * 256 <= w * 0.8 and (y2 - y1) * 256 <= h * 0.8:
            zoom = z
            break
    cx, cy = _deg2tile((max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2, zoom)
    left, top = cx * 256 - w / 2, cy * 256 - h / 2
    canvas = Image.new("RGB", size, (235, 235, 235))
    fetched = 0
    for tx in range(int(left // 256), int((left + w) // 256) + 1):
        for ty in range(int(top // 256), int((top + h) // 256) + 1):
            if not 0 <= ty < 2 ** zoom:
                continue
            tile = _tile(zoom, tx % (2 ** zoom), ty)
            if tile is not None:
                canvas.paste(tile, (int(tx * 256 - left), int(ty * 256 - top)))
                fetched += 1
    if not fetched:
        return None
    draw = ImageDraw.Draw(canvas)
    for number, (lat, lon) in enumerate(points, 1):
        px, py = _deg2tile(lat, lon, zoom)
        x, y = px * 256 - left, py * 256 - top
        draw.ellipse((x - 26, y - 26, x + 26, y + 26), fill=_PINK, outline="white", width=5)
        label = str(number)
        font = _font(28, "bold")
        draw.text((x - draw.textlength(label, font=font) / 2, y - 18), label, font=font, fill="white")
    draw.rectangle((w - 330, h - 34, w, h), fill=(255, 255, 255))
    draw.text((w - 320, h - 30), "© OpenStreetMap contributors", font=_font(20), fill=_INK)
    return canvas


def _map_slide(plan: dict) -> Image.Image | None:
    stops = (plan.get("review") or {}).get("stops") or plan.get("checks", [])
    placed, seen = [], set()
    for c in stops:
        if c.get("lat") is None or c.get("lon") is None or c["name"] in seen:
            continue
        if c.get("status") == "far":
            continue  # a wrong-city match would zoom the map out to nothing
        seen.add(c["name"])
        placed.append(c)
    placed = placed[:14]
    if not placed:
        return None
    w, h = SLIDE_SIZE
    image = _gradient(SLIDE_SIZE)
    draw = ImageDraw.Draw(image)
    draw.text((70, 70), f"{len(placed)} stops, found on the map", font=_font(56, "bold"), fill="white")
    picture = _map([(c["lat"], c["lon"]) for c in placed], (w - 140, 760))
    if picture is None:
        return None
    mask = Image.new("L", picture.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *picture.size), radius=36, fill=255)
    image.paste(picture, (70, 170), mask)
    y = 960
    for number, check in enumerate(placed[:6], 1):
        y = _text_block(draw, (70, y), f"{number}. {check['name']}", _font(34, "bold"), "white", w - 140, 1, 1.35)
    _footer(draw, SLIDE_SIZE)
    return image


def _closing() -> Image.Image:
    w, h = SLIDE_SIZE
    image = _gradient(SLIDE_SIZE)
    draw = ImageDraw.Draw(image)
    y = _text_block(draw, (90, 380), "Did an AI plan your trip?", _font(84, "bold"), "white", w - 180, 2, 1.1)
    y = _text_block(
        draw, (90, y + 30),
        "Paste the plan. ReelTrip looks up each place on the map and flags closed days, "
        "wrong cities and days that don't fit.",
        _font(46), "white", w - 180, 5,
    )
    _text_block(draw, (90, y + 50), "Free, no account.", _font(46, "bold"), "white", w - 180, 1)
    _footer(draw, SLIDE_SIZE)
    return image


def slides(plan: dict) -> list[bytes]:
    """The carousel as PNG bytes, in posting order."""
    days = _days(plan)[:MAX_DAY_SLIDES]
    middle = [_day_slide(plan, d) for d in days]
    map_slide = _map_slide(plan)
    if map_slide is not None:
        middle.append(map_slide)
    count = len(middle) + 2
    images = [_cover(plan, count), *middle, _closing()]
    return [_png(i) for i in images]
