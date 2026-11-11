"""Offline tests for the web app's pages, limits and small helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from voyagent import holidays, limits, routes, stats, storage  # noqa: E402
from voyagent.jobs import CheckJob  # noqa: E402
from voyagent.web import app as web  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.setattr(stats, "_memory", {})
    monkeypatch.setattr(limits, "_counts", {})
    monkeypatch.setattr(web, "_require_config", lambda: None)
    monkeypatch.setattr(CheckJob, "start", lambda self: self)  # don't run the check
    monkeypatch.setattr(web, "_checks", {})
    return TestClient(web.app)


def test_public_pages_render(client):
    for path in ("/", "/check/chatgpt", "/c/example", "/closed-days", "/privacy", "/robots.txt", "/sitemap.xml"):
        assert client.get(path).status_code == 200, path
    assert client.head("/").status_code == 200
    assert "ChatGPT planned your trip" in client.get("/check/chatgpt").text
    assert "<title>Check a ChatGPT itinerary" in client.get("/check/chatgpt").text
    assert "<title>TripCorrect · The reality check for trip plans</title>" in client.get("/").text
    assert client.get("/check/nonsense").status_code == 404
    assert "Louvre Museum" in client.get("/closed-days").text
    assert "/check/gemini" in client.get("/sitemap.xml").text


def test_check_carries_the_advisor_name_and_counts_usage(client):
    text = "Day 1: Bardo National Museum, then lunch at Dar El Jeld in the Medina of Tunis."
    job = client.post("/api/checks", json={"text": text, "prepared_by": "  Atlas   Voyages "}).json()
    assert job["prepared_by"] == "Atlas Voyages" and job["status"] == "queued"
    assert client.post("/api/checks", json={"text": "too short"}).status_code == 422
    rows = {r["label"]: r["total"] for r in stats.read(2)["rows"]}
    assert rows["Checks started"] == 1


def test_fix_needs_a_report_with_problems(client, monkeypatch):
    text = "Day 1: Bardo National Museum, then lunch at Dar El Jeld in the Medina of Tunis."
    job = client.post("/api/checks/example/fix", json={"text": text}).json()
    assert job["status"] == "queued" and job["before"]["problems"] >= 1
    clean = {**web._example_check(), "report": {**web._example_check()["report"], "fix_prompt": ""}}
    monkeypatch.setattr(web, "_load_check", lambda job_id: clean)
    assert client.post("/api/checks/example/fix", json={"text": text}).status_code == 422


def test_daily_limit_per_visitor(client, monkeypatch):
    monkeypatch.setattr(limits, "CHECKS_PER_IP", 2)
    text = "Day 1: Bardo National Museum, then lunch at Dar El Jeld in the Medina of Tunis."
    codes = [client.post("/api/checks", json={"text": text}).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


def test_stats_page_is_hidden_without_the_key(client, monkeypatch):
    assert client.get("/stats").status_code == 404
    monkeypatch.setattr(web, "STATS_KEY", "s3cret")
    assert client.get("/stats?key=wrong").status_code == 404
    client.post("/api/feedback", json={"vote": "up"})
    page = client.get("/stats?key=s3cret")
    assert page.status_code == 200 and "Thumbs up" in page.text
    assert client.post("/api/feedback", json={"vote": "sideways"}).status_code == 422


def test_routes_and_holidays_fail_soft(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(routes, "_memory", {})
    monkeypatch.setattr(holidays, "_memory", {})

    def down(*args, **kwargs):
        raise routes.requests.ConnectionError("no network")

    monkeypatch.setattr(routes.requests, "get", down)
    assert routes.drive([(36.8, 10.18), (35.67, 10.1)]) is None
    assert routes.drive([(36.8, 10.18)]) is None
    assert holidays.public_holidays("tn", 2026) == {}
    assert holidays.public_holidays("", 2026) == {}
    assert routes.hours_minutes(200) == "3 h 20 min" and routes.hours_minutes(45) == "45 min"
