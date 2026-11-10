"""ReelTrip web app: JSON API, website pages and the MCP server in one process.

Run locally:   uvicorn voyagent.web.app:app --reload
               (or: python -m voyagent.web)

Routes:
- ``/``                 the home page: check an itinerary, or plan from TikTok
- ``/c/{id}``           a shareable itinerary check report (``/c/example`` ships with the app)
- ``/p/{id}``           a shareable, server-rendered page for a finished plan
- ``/p/{id}/post``      the plan as a ready-to-post carousel and caption
- ``/p/{id}/og.png``    link preview image; ``/p/{id}/plan.ics`` calendar export
- ``/api/checks``       start an itinerary check; poll ``/api/checks/{id}``
- ``/api/discover``     TikTok-inspired spots for a destination (seconds)
- ``/api/plans``        start a plan (a minute or two); poll ``/api/plans/{id}``
- ``/mcp``              the ReelTrip MCP server (streamable HTTP)
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import threading
import time
import zipfile
from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

from voyagent import config, content, exports, limits, share_images, social, storage
from voyagent.config import MissingConfigError, validate_env
from voyagent.jobs import LANGUAGES, PHASES, CheckJob, PlanJob
from voyagent.mcp_server import mcp

_HERE = Path(__file__).resolve().parent
#: Plans are heavy; cap how many run at once on a small free host.
MAX_ACTIVE_PLANS = int(os.environ.get("VOYAGENT_MAX_ACTIVE_PLANS", "2"))
#: Checks are lighter (one model call, then lookups).
MAX_ACTIVE_CHECKS = int(os.environ.get("VOYAGENT_MAX_ACTIVE_CHECKS", "3"))
#: Optional donation page (Ko-fi, GitHub Sponsors, ...) shown after a plan.
SUPPORT_URL = os.environ.get("VOYAGENT_SUPPORT_URL", "")
#: Where people can report a problem (shown on the privacy page and footer).
CONTACT_URL = os.environ.get(
    "VOYAGENT_CONTACT_URL", "https://github.com/Abdelkerim-Dassi/trip-planner-Agent/issues"
)
MAX_DISCOVER_CITIES = 3
MAX_CHECK_CHARS = 20000
#: Finished jobs stay in memory this long; after that they are read from storage.
JOB_MEMORY_SECONDS = 3600
_JOB_ID = re.compile(r"^[0-9a-f]{12}$")
_LIMIT_MESSAGE = "You've reached today's free limit. It resets at midnight UTC."

templates = Jinja2Templates(directory=_HERE / "templates")
_plans: dict[str, PlanJob] = {}
_checks: dict[str, CheckJob] = {}
_jobs_lock = threading.Lock()
#: Finished jobs already written to storage.
_saved: set[str] = set()


def _allowed_hosts() -> list[str]:
    """Hosts the MCP endpoint answers to (DNS-rebinding protection).

    Render sets RENDER_EXTERNAL_HOSTNAME and Hugging Face Spaces sets SPACE_HOST;
    add others with VOYAGENT_PUBLIC_HOSTS.
    """
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    extra = [os.environ.get("RENDER_EXTERNAL_HOSTNAME", ""), os.environ.get("SPACE_HOST", "")]
    extra += os.environ.get("VOYAGENT_PUBLIC_HOSTS", "").split(",")
    return hosts + [h.strip() for h in extra if h.strip()]


_mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts(),
        allowed_origins=[f"https://{h}" for h in _allowed_hosts() if "*" not in h]
        + ["http://localhost:*", "http://127.0.0.1:*"],
    ),
)


@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI):
    # The mounted MCP app's session manager must run for the app's lifetime.
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="ReelTrip", lifespan=_lifespan, docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")


# --- Helpers -----------------------------------------------------------------


def _require_config() -> None:
    try:
        validate_env()
    except MissingConfigError as exc:
        raise HTTPException(503, str(exc)) from exc


def _limit(kind: str, request: Request, per_day: int) -> None:
    if not limits.allow(kind, limits.client_ip(request), per_day):
        raise HTTPException(429, _LIMIT_MESSAGE)


def _prune(jobs: dict) -> None:
    """Forget finished jobs after a while (call with the lock held)."""
    cutoff = time.time() - JOB_MEMORY_SECONDS
    for job_id in [i for i, j in jobs.items() if j.status in ("done", "error") and j.created < cutoff]:
        if jobs[job_id].status == "done" and job_id not in _saved:
            continue  # not stored yet: keep it until someone reads it
        del jobs[job_id]
        _saved.discard(job_id)


def _load(kind: str, jobs: dict, job_id: str) -> dict | None:
    """A job's state: from memory while it runs, from storage afterwards."""
    if not _JOB_ID.match(job_id):
        return None
    with _jobs_lock:
        job = jobs.get(job_id)
    if job is not None:
        data = job.to_dict()
        if job.status == "done" and job.id not in _saved:
            storage.save(kind, job.id, data)
            _saved.add(job.id)
        return data
    return storage.load(kind, job_id)


def _load_plan(job_id: str) -> dict | None:
    return _load("plans", _plans, job_id)


@lru_cache(maxsize=1)
def _example_check() -> dict:
    """The report behind /c/example: a real check, shipped with the app so the
    first visitor sees a result without waiting or spending anything."""
    path = _HERE / "examples" / "check.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_check(job_id: str) -> dict | None:
    if job_id == "example":
        return _example_check()
    return _load("reviews", _checks, job_id)


# --- API ---------------------------------------------------------------------


class DiscoverRequest(BaseModel):
    destinations: str = Field("", description="Comma-separated places, e.g. 'Tunis, Djerba'")
    month: str = ""
    interests: str = ""
    links: list[str] = Field(default_factory=list, description="TikTok post URLs")
    captions: list[str] = Field(default_factory=list, description="Pasted caption text")


class PlanRequest(BaseModel):
    origin: str = ""
    cities: str
    start: date
    end: date
    interests: str = ""
    inspiration: str = ""
    halal: bool = False
    language: str = Field("en", description="en, fr or ar")


class CheckRequest(BaseModel):
    text: str = Field(description="The itinerary to check, as plain text")
    start: date | None = Field(None, description="First day of the trip, to match closing days to weekdays")
    halal: bool = False
    destination: str = ""


@app.post("/api/checks", status_code=202)
def start_check(req: CheckRequest, request: Request) -> dict:
    """Check an itinerary against the map and published opening days."""
    _require_config()
    text = req.text.strip()
    if len(text) < 40:
        raise HTTPException(422, "Paste the itinerary itself: the day-by-day plan with its places.")
    if len(text) > MAX_CHECK_CHARS:
        raise HTTPException(422, f"That's too long to check at once (limit {MAX_CHECK_CHARS:,} characters).")
    _limit("check", request, limits.CHECKS_PER_IP)
    with _jobs_lock:
        _prune(_checks)
        active = sum(j.status in ("queued", "running") for j in _checks.values())
        if active >= MAX_ACTIVE_CHECKS:
            raise HTTPException(429, "ReelTrip is checking other trips right now. Please try again in a minute.")
        job = CheckJob(text, req.start, req.halal, req.destination.strip()[:80])
        _checks[job.id] = job
    return job.start().to_dict()


@app.get("/api/checks/{job_id}")
def check_status(job_id: str) -> dict:
    data = _load_check(job_id)
    if data is None:
        raise HTTPException(404, "Check not found.")
    return data


@app.post("/api/discover")
def discover(req: DiscoverRequest, request: Request) -> dict:
    """TikTok-inspired, OpenStreetMap-verified spots (runs in a worker thread)."""
    _require_config()
    _limit("discover", request, limits.DISCOVERS_PER_IP)
    destinations = [d.strip() for d in req.destinations.split(",") if d.strip()]
    results = [
        social.trending_spots(d, req.month, req.interests).to_dict()
        for d in destinations[:MAX_DISCOVER_CITIES]
    ]
    if req.links or req.captions:
        anchor = destinations[0] if len(destinations) == 1 else ""
        from_links = social.spots_from_links(req.links, anchor, captions=req.captions).to_dict()
        from_links["destination"] = "Your saved TikToks"
        results.insert(0, from_links)
    return {"results": results}


@app.post("/api/plans", status_code=202)
def start_plan(req: PlanRequest, request: Request) -> dict:
    _require_config()
    if req.end < req.start:
        raise HTTPException(422, "The trip must end after it starts.")
    if (req.end - req.start).days > 20:
        raise HTTPException(422, "Plans cover up to three weeks. Shorten the dates or split the trip.")
    if not req.cities.strip():
        raise HTTPException(422, "Please say where you're going.")
    _limit("plan", request, limits.PLANS_PER_IP)
    with _jobs_lock:
        _prune(_plans)
        active = sum(j.status in ("queued", "running") for j in _plans.values())
        if active >= MAX_ACTIVE_PLANS:
            raise HTTPException(
                429, "ReelTrip is planning other trips right now. Please try again in a few minutes."
            )
        job = PlanJob(
            req.origin.strip() or "not given",
            req.cities.strip(),
            f"{req.start:%d %B %Y} - {req.end:%d %B %Y}",
            req.interests.strip() or "the highlights, local food",
            req.inspiration.strip(),
            halal=req.halal,
            language=req.language if req.language in LANGUAGES else "en",
        )
        _plans[job.id] = job
    return job.start().to_dict()


@app.get("/api/plans/{job_id}")
def plan_status(job_id: str) -> dict:
    data = _load_plan(job_id)
    if data is None:
        raise HTTPException(404, "Plan not found.")
    return data


@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz() -> dict:
    # Model names only, never keys: lets you confirm which free setup is live.
    return {
        "ok": True,
        "plan_mode": config.PLAN_MODE,
        "model": config.litellm_model(),
        "discovery_model": config.discovery_model(),
        "fallback_models": config.fallback_models(),
        "helper_model": config.helper_model(),
        "plans_persist": storage.is_remote(),
        "second_search_provider": bool(os.environ.get("TAVILY_API_KEY")),
    }


# --- Pages -------------------------------------------------------------------


def _public_url(request: Request) -> str:
    """This site's address as visitors see it (Render serves us behind a proxy)."""
    base = os.environ.get("VOYAGENT_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    return (base or str(request.base_url)).rstrip("/")


def _page(request: Request, name: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        name,
        {
            "support_url": SUPPORT_URL,
            "contact_url": CONTACT_URL,
            "public_url": _public_url(request),
            **context,
        },
    )


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index(request: Request):
    return _page(request, "index.html", phases=[f"{i} {label}" for i, label in PHASES])


@app.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return _page(request, "privacy.html")


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request) -> str:
    # Reports and plans are shared by link; they are not for search engines.
    return (
        "User-agent: *\nAllow: /$\nAllow: /c/example\nAllow: /privacy\n"
        "Disallow: /p/\nDisallow: /c/\nDisallow: /api/\nDisallow: /mcp\n"
        f"Sitemap: {_public_url(request)}/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
def sitemap(request: Request) -> Response:
    base = _public_url(request)
    urls = "".join(f"<url><loc>{base}{path}</loc></url>" for path in ("/", "/c/example", "/privacy"))
    return Response(
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
        media_type="application/xml",
    )


_IMAGE_HEADERS = {"Cache-Control": "public, max-age=86400"}


@app.get("/og.png")
def home_og_image() -> Response:
    return Response(share_images.home_card(), media_type="image/png", headers=_IMAGE_HEADERS)


# --- Itinerary check pages ------------------------------------------------------


def _finished_check(job_id: str) -> dict:
    data = _load_check(job_id)
    if data is None or data.get("status") != "done" or not data.get("report"):
        raise HTTPException(404, "This check doesn't exist or isn't finished yet.")
    return data


@app.get("/c/{job_id}", response_class=HTMLResponse)
def shared_check(request: Request, job_id: str):
    data = _finished_check(job_id)
    return _page(
        request,
        "check.html",
        check=data,
        report=data["report"],
        checked_on=f"{date.fromtimestamp(data.get('created') or time.time()):%d %B %Y}",
        is_example=job_id == "example",
    )


@app.get("/c/{job_id}/og.png")
def check_og_image(job_id: str) -> Response:
    return Response(
        share_images.report_card(_finished_check(job_id)["report"]),
        media_type="image/png",
        headers=_IMAGE_HEADERS,
    )


# --- Plan pages --------------------------------------------------------------------


def _finished(job_id: str) -> dict:
    data = _load_plan(job_id)
    if data is None or data["status"] != "done":
        raise HTTPException(404, "This plan doesn't exist or isn't finished yet.")
    return data


@lru_cache(maxsize=16)
def _slides(job_id: str) -> tuple[bytes, ...]:
    # Finished plans don't change, so their slides are rendered once.
    return tuple(share_images.slides(_finished(job_id)))


@app.get("/p/{job_id}", response_class=HTMLResponse)
def shared_plan(request: Request, job_id: str):
    return _page(request, "plan.html", plan=_finished(job_id))


@app.get("/p/{job_id}/og.png")
def plan_og_image(job_id: str) -> Response:
    return Response(share_images.og_card(_finished(job_id)), media_type="image/png", headers=_IMAGE_HEADERS)


@app.get("/p/{job_id}/slide/{number}.png")
def plan_slide(job_id: str, number: int) -> Response:
    slides = _slides(job_id)
    if not 1 <= number <= len(slides):
        raise HTTPException(404, "No such slide.")
    return Response(slides[number - 1], media_type="image/png", headers=_IMAGE_HEADERS)


@app.get("/p/{job_id}/slides.zip")
def plan_slides_zip(job_id: str) -> Response:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as archive:
        for number, png in enumerate(_slides(job_id), 1):
            archive.writestr(f"reeltrip-{job_id}-{number:02d}.png", png)
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="reeltrip-{job_id}-slides.zip"'},
    )


@app.get("/p/{job_id}/plan.ics")
def plan_calendar(request: Request, job_id: str) -> Response:
    data = _finished(job_id)
    return Response(
        exports.to_ics(data, f"{_public_url(request)}/p/{job_id}"),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="reeltrip-{job_id}.ics"'},
    )


@app.get("/api/plans/{job_id}/social")
def plan_social(job_id: str) -> dict:
    """A ready-to-post caption for the plan, written once and then kept."""
    _finished(job_id)
    cached = storage.load("social", job_id)
    if cached:
        return cached
    post = content.social_post(_finished(job_id))
    if not post:
        raise HTTPException(503, "Couldn't write a caption right now. Try again in a minute.")
    storage.save("social", job_id, post)
    return post


@app.get("/p/{job_id}/post", response_class=HTMLResponse)
def plan_post(request: Request, job_id: str):
    return _page(request, "post.html", plan=_finished(job_id), slide_count=len(_slides(job_id)))


# Last: everything else (the /mcp endpoint) is handled by the MCP app.
app.mount("/", _mcp_app)
