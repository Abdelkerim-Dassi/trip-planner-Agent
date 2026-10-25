"""ReelTrip web app: JSON API, website pages and the MCP server in one process.

Run locally:   uvicorn voyagent.web.app:app --reload
               (or: python -m voyagent.web)

Routes:
- ``/``                 the planner page
- ``/p/{id}``           a shareable, server-rendered page for a finished plan
- ``/api/discover``     TikTok-inspired spots for a destination (seconds)
- ``/api/plans``        start a full crew plan (minutes); poll ``/api/plans/{id}``
- ``/mcp``              the ReelTrip MCP server (streamable HTTP)
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

from voyagent import social
from voyagent.config import MissingConfigError, validate_env
from voyagent.jobs import PHASES, PlanJob
from voyagent.mcp_server import mcp

_HERE = Path(__file__).resolve().parent
#: Where finished plans are saved so share links outlive the process.
DATA_DIR = Path(os.environ.get("VOYAGENT_DATA_DIR", "data")) / "plans"
#: Crew runs are heavy; cap how many run at once on a small free host.
MAX_ACTIVE_PLANS = int(os.environ.get("VOYAGENT_MAX_ACTIVE_PLANS", "2"))
#: Optional donation page (Ko-fi, GitHub Sponsors, ...) shown after a plan.
SUPPORT_URL = os.environ.get("VOYAGENT_SUPPORT_URL", "")
MAX_DISCOVER_CITIES = 3
_JOB_ID = re.compile(r"^[0-9a-f]{12}$")

templates = Jinja2Templates(directory=_HERE / "templates")
_jobs: dict[str, PlanJob] = {}
_jobs_lock = threading.Lock()


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


def _save(job: PlanJob) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{job.id}.json").write_text(json.dumps(job.to_dict()), encoding="utf-8")


def _load(job_id: str) -> dict | None:
    if not _JOB_ID.match(job_id):
        return None
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is not None:
        if job.status == "done" and not (DATA_DIR / f"{job.id}.json").exists():
            _save(job)
        return job.to_dict()
    path = DATA_DIR / f"{job_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# --- API ---------------------------------------------------------------------


class DiscoverRequest(BaseModel):
    destinations: str = Field("", description="Comma-separated places, e.g. 'Tunis, Djerba'")
    month: str = ""
    interests: str = ""
    links: list[str] = Field(default_factory=list, description="TikTok post URLs")
    captions: list[str] = Field(default_factory=list, description="Pasted caption text")


class PlanRequest(BaseModel):
    origin: str
    cities: str
    start: date
    end: date
    interests: str
    inspiration: str = ""


@app.post("/api/discover")
def discover(req: DiscoverRequest) -> dict:
    """TikTok-inspired, OpenStreetMap-verified spots (runs in a worker thread)."""
    _require_config()
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
def start_plan(req: PlanRequest) -> dict:
    _require_config()
    if req.end < req.start:
        raise HTTPException(422, "The trip must end after it starts.")
    if not all(s.strip() for s in (req.origin, req.cities, req.interests)):
        raise HTTPException(422, "Please fill in where from, destinations and interests.")
    with _jobs_lock:
        active = sum(j.status in ("queued", "running") for j in _jobs.values())
        if active >= MAX_ACTIVE_PLANS:
            raise HTTPException(
                429, "ReelTrip is planning other trips right now. Please try again in a few minutes."
            )
        job = PlanJob(
            req.origin.strip(),
            req.cities.strip(),
            f"{req.start:%d %B %Y} - {req.end:%d %B %Y}",
            req.interests.strip(),
            req.inspiration.strip(),
        )
        _jobs[job.id] = job
    return job.start().to_dict()


@app.get("/api/plans/{job_id}")
def plan_status(job_id: str) -> dict:
    data = _load(job_id)
    if data is None:
        raise HTTPException(404, "Plan not found.")
    return data


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# --- Pages -------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"phases": [f"{i} {label}" for i, label in PHASES], "support_url": SUPPORT_URL},
    )


@app.get("/p/{job_id}", response_class=HTMLResponse)
def shared_plan(request: Request, job_id: str):
    data = _load(job_id)
    if data is None or data["status"] != "done":
        raise HTTPException(404, "This plan doesn't exist or isn't finished yet.")
    return templates.TemplateResponse(
        request, "plan.html", {"plan": data, "support_url": SUPPORT_URL}
    )


# Last: everything else (the /mcp endpoint) is handled by the MCP app.
app.mount("/", _mcp_app)
