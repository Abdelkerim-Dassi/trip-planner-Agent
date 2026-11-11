"""End-to-end launch check for a running TripCorrect deployment.

Exercises every public surface the way a visitor (or an AI assistant) would:
pages, input validation, TikTok discovery, pasted links, plan jobs, share
pages, the MCP endpoint and its host protection. Prints one PASS/FAIL line per
check and exits non-zero if anything failed.

    python scripts/launch_check.py                       # https://reeltrip.onrender.com
    python scripts/launch_check.py http://127.0.0.1:8000 # a local server
    python scripts/launch_check.py --full                # also run one full plan (minutes, costs LLM tokens)

Discovery checks spend a few Serper searches and LLM calls each.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date, timedelta

import requests

DEFAULT_URL = "https://reeltrip.onrender.com"
TIMEOUT = 180

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  - ' + detail if detail else ''}", flush=True)
    return ok


def post(base: str, path: str, body: dict, **kw) -> requests.Response:
    return requests.post(base + path, json=body, timeout=TIMEOUT, **kw)


def run_pages(base: str) -> None:
    t0 = time.time()
    r = requests.get(base + "/healthz", timeout=TIMEOUT)
    check("health check answers", r.status_code == 200, f"{time.time() - t0:.1f}s (includes wake-up if asleep)")

    t0 = time.time()
    r = requests.get(base + "/", timeout=TIMEOUT)
    html = r.text
    check("home page loads", r.status_code == 200, f"{time.time() - t0:.2f}s, {len(html) // 1024} KB")
    check("home page is branded TripCorrect", "<title>TripCorrect" in html)
    check("home page has social preview tags", 'property="og:title"' in html)
    check("home page has phone viewport", 'name="viewport"' in html)
    for asset in ("/static/app.js", "/static/style.css"):
        check(f"asset {asset} loads", requests.get(base + asset, timeout=TIMEOUT).status_code == 200)
    check("API docs page loads", requests.get(base + "/api/docs", timeout=TIMEOUT).status_code == 200)
    check("HEAD / answers (uptime monitors use it)", requests.head(base + "/", timeout=TIMEOUT).status_code == 200)
    r = requests.get(base + "/c/example", timeout=TIMEOUT)
    check("example report page renders", r.status_code == 200 and "Itinerary check" in r.text, str(r.status_code))
    for path in ("/og.png", "/c/example/og.png"):
        r = requests.get(base + path, timeout=TIMEOUT)
        check(f"preview image {path} is a PNG", r.status_code == 200 and r.content[1:4] == b"PNG", str(r.status_code))
    check("privacy page loads", requests.get(base + "/privacy", timeout=TIMEOUT).status_code == 200)
    r = requests.get(base + "/check/chatgpt", timeout=TIMEOUT)
    check("assistant landing page renders", r.status_code == 200 and "Check a ChatGPT itinerary" in r.text)
    r = requests.get(base + "/closed-days", timeout=TIMEOUT)
    check("closed-days page lists sourced sights", r.status_code == 200 and "Official page" in r.text)
    check("usage page is hidden without its key", requests.get(base + "/stats", timeout=TIMEOUT).status_code == 404)
    r = post(base, "/api/feedback", {"vote": "up"})
    check("feedback is accepted", r.status_code == 200, str(r.status_code))
    r = requests.get(base + "/robots.txt", timeout=TIMEOUT)
    check("robots.txt keeps shared plans out of search", r.status_code == 200 and "Disallow: /p/" in r.text)


def run_validation(base: str) -> None:
    start = date.today() + timedelta(days=30)
    good = {"origin": "Paris", "cities": "Tunis", "start": str(start), "end": str(start + timedelta(days=3)), "interests": "food"}

    r = post(base, "/api/plans", {**good, "end": str(start - timedelta(days=1))})
    check("rejects end date before start", r.status_code == 422, str(r.status_code))
    r = post(base, "/api/plans", {**good, "cities": "  "})
    check("rejects blank destination", r.status_code == 422, str(r.status_code))
    r = post(base, "/api/checks", {"text": "too short"})
    check("rejects an itinerary that is too short", r.status_code == 422, str(r.status_code))
    r = requests.get(base + "/api/checks/doesnotexist", timeout=TIMEOUT)
    check("unknown check id gives 404", r.status_code == 404, str(r.status_code))
    r = post(base, "/api/plans", {**good, "start": "not-a-date"})
    check("rejects malformed date", r.status_code == 422, str(r.status_code))
    r = requests.get(base + "/api/plans/doesnotexist", timeout=TIMEOUT)
    check("unknown plan id gives 404", r.status_code == 404, str(r.status_code))
    r = requests.get(base + "/api/plans/../../etc/passwd", timeout=TIMEOUT)
    check("path traversal in plan id is refused", r.status_code in (404, 400), str(r.status_code))
    r = requests.get(base + "/p/abcdef123456", timeout=TIMEOUT)
    check("unknown share page gives 404", r.status_code == 404, str(r.status_code))


def run_discovery(base: str) -> None:
    def discover(body: dict) -> tuple[dict, float]:
        t0 = time.time()
        r = post(base, "/api/discover", body)
        r.raise_for_status()
        return r.json(), time.time() - t0

    data, secs = discover({"destinations": "Tozeur", "month": "December", "interests": "desert"})
    group = data["results"][0]
    names = [s["name"] for s in group["spots"]]
    check("TikTok discovery returns videos", len(group["videos"]) >= 10, f"{len(group['videos'])} videos in {secs:.0f}s")
    check("TikTok discovery returns verified spots", len(names) >= 3, ", ".join(names))
    check("discovery finishes within 60s", secs < 60, f"{secs:.0f}s")
    check("every spot has map coordinates", all(s["lat"] is not None for s in group["spots"]))
    check("every spot links back to its videos", all(s["videos"] for s in group["spots"]))
    check("destination itself isn't listed as a spot", "Tozeur" not in names)

    data, _ = discover({"destinations": "Djerba, Tozeur, Tunis, Sousse"})
    check("caps discovery at 3 destinations", len(data["results"]) == 3, f"{len(data['results'])} groups")

    data, _ = discover({"destinations": "Lisbon", "month": "May"})
    check("works outside North Africa (Lisbon)", len(data["results"][0]["spots"]) >= 2,
          ", ".join(s["name"] for s in data["results"][0]["spots"][:5]))

    data, _ = discover({"destinations": "Qwxzyville"})
    g = data["results"][0]
    check("nonsense destination fails gracefully", isinstance(g["spots"], list), f"{len(g['spots'])} spots, notes={g['notes'][:1]}")

    links = [
        "https://www.tiktok.com/@traveldestination.journy/video/7647453189742136609",
        "https://example.com/not-tiktok",
        "https://www.tiktok.com/@nobody/video/1",
    ]
    data, _ = discover({"destinations": "", "links": links})
    g = data["results"][0]
    check("pasted TikTok link becomes a spot", any("Sidi Bou" in s["name"] for s in g["spots"]),
          ", ".join(s["name"] for s in g["spots"]))
    check("non-TikTok link is reported, not crashed", any("Not a TikTok link" in n for n in g["notes"]))
    check("unreadable TikTok link is reported", any("Couldn't read" in n for n in g["notes"]))


PARIS = (
    "3 days in Paris. Day 1: Louvre Museum in the morning, lunch at Bouillon Chartier, then the "
    "Tuileries Garden. Day 2: Palace of Versailles. Day 3: Musee d'Orsay, lunch at Chez Luminara "
    "Bistro, Eiffel Tower at sunset."
)
PARIS_START = "2026-12-15"  # a Tuesday: the Louvre is closed


def run_check(base: str) -> None:
    r = post(base, "/api/checks", {"text": PARIS, "start": PARIS_START})
    if not check("itinerary check starts", r.status_code == 202, str(r.status_code)):
        return
    job_id, t0 = r.json()["id"], time.time()
    while time.time() - t0 < 300:
        job = requests.get(f"{base}/api/checks/{job_id}", timeout=TIMEOUT).json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(3)
    secs = time.time() - t0
    if not check("itinerary check finishes", job["status"] == "done", f"{job['status']} in {secs:.0f}s {job.get('error', '')[:120]}"):
        return
    report = job["report"]
    issues = {(i["kind"], i["stop"]) for i in report["issues"]}
    check("check finishes within 90s", secs < 90, f"{secs:.0f}s")
    check("catches the Louvre on a Tuesday", ("closed", "Louvre Museum") in issues, str(sorted(issues))[:150])
    check("flags the invented restaurant", any(k == "no_trace" and "Luminara" in s for k, s in issues))
    summary = report["summary"]
    check("most places are found on the map", summary["confirmed"] >= summary["places"] - 2,
          f"{summary['confirmed']} of {summary['places']}")
    check("report offers a fix list", "Louvre" in report["fix_prompt"])
    r = post(base, f"/api/checks/{job_id}/fix", {"text": PARIS})
    if check("fix starts", r.status_code == 202, str(r.status_code)):
        fix_id, t0 = r.json()["id"], time.time()
        while time.time() - t0 < 300:
            fixed = requests.get(f"{base}/api/checks/{fix_id}", timeout=TIMEOUT).json()
            if fixed["status"] in ("done", "error"):
                break
            time.sleep(3)
        ok = fixed["status"] == "done"
        check("fix finishes with a rewritten itinerary", ok and len(fixed["fixed_text"]) > 100,
              f"{fixed['status']} in {time.time() - t0:.0f}s {fixed.get('error', '')[:100]}")
        if ok:
            after = fixed["report"]["summary"]["problems"]
            check("rewrite has fewer problems than the original", after < summary["problems"],
                  f"{summary['problems']} -> {after}")
            check("the Louvre is no longer on its closed day",
                  not any(i["kind"] == "closed" and "Louvre" in i["stop"] for i in fixed["report"]["issues"]))
    r = requests.get(f"{base}/c/{job_id}", timeout=TIMEOUT)
    check("shared report page renders", r.status_code == 200 and "noindex" in r.text, str(r.status_code))


def run_mcp(base: str) -> None:
    r = requests.post(base + "/mcp", data="{}", timeout=TIMEOUT,
                      headers={"Host": "evil.example", "Content-Type": "application/json"})
    check("MCP rejects unknown Host header", r.status_code in (403, 421), str(r.status_code))

    async def session_checks() -> None:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(base + "/mcp") as streams:
            async with ClientSession(streams[0], streams[1]) as s:
                init = await s.initialize()
                check("MCP server identifies as tripcorrect", init.server_info.name == "tripcorrect", init.server_info.name)
                tools = [t.name for t in (await s.list_tools()).tools]
                check("MCP lists its 7 tools", len(tools) == 7, ", ".join(tools))
                check("MCP offers check_itinerary and not the slow planner",
                      "check_itinerary" in tools and "plan_trip" not in tools)
                calls = {
                    "verify_place": {"name": "Bardo Museum", "near": "Tunisia"},
                    "typical_weather": {"place": "Tozeur", "month": "December"},
                    "prayer_times": {"place": "Kairouan", "date": "2026-12-12"},
                    "transfer_options": {"origin": "Tunis", "destination": "Sousse"},
                    "check_itinerary": {"itinerary": PARIS, "start_date": PARIS_START},
                }
                for name, args in calls.items():
                    res = await s.call_tool(name, args)
                    text = res.content[0].text if res.content else ""
                    check(f"MCP tool {name} works", not res.is_error and len(text) > 20, text[:70].replace("\n", " "))

    try:
        asyncio.run(session_checks())
    except Exception as exc:  # report, don't abort the run
        check("MCP session", False, f"{type(exc).__name__}: {exc}"[:200])


def run_full_plan(base: str) -> None:
    start = date.today() + timedelta(days=40)
    body = {"cities": "Tunis", "start": str(start), "end": str(start + timedelta(days=2)),
            "interests": "history, food", "inspiration": "- Sidi Bou Said: blue-and-white village [3 videos]"}
    r = post(base, "/api/plans", body)
    if not check("plan job starts", r.status_code == 202, str(r.status_code)):
        return
    job_id, t0, phases_seen = r.json()["id"], time.time(), set()
    while time.time() - t0 < 1800:
        job = requests.get(f"{base}/api/plans/{job_id}", timeout=TIMEOUT).json()
        phases_seen.add(job["completed"])
        if job["status"] in ("done", "error"):
            break
        time.sleep(15)
    mins = (time.time() - t0) / 60
    check("full plan finishes without error", job["status"] == "done", f"{job['status']} in {mins:.1f} min {job.get('error', '')[:150]}")
    check("progress advanced through phases", len(phases_seen) >= 3, f"saw {sorted(phases_seen)}")
    if job["status"] != "done":
        return
    plan = job["result"]
    days = sum(f"Day {i}" in plan for i in range(1, 4))
    check("plan covers every travel day", days == 3, f"{days}/3 day sections, {len(plan)} chars")
    check("plan includes the TikTok spot", "Sidi Bou" in plan)
    review = job.get("review") or {}
    check("plan comes with its check report", bool(review.get("summary", {}).get("places")),
          str(review.get("summary"))[:120])
    r = requests.get(f"{base}/p/{job_id}", timeout=TIMEOUT)
    check("share page renders the plan", r.status_code == 200 and "Shared trip plan" in r.text, str(r.status_code))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base_url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--full", action="store_true", help="also run one full plan")
    parser.add_argument("--skip-discovery", action="store_true", help="skip checks that spend search credits")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    print(f"Checking {base}\n", flush=True)

    sections = [run_pages, run_validation, run_mcp]
    if not args.skip_discovery:
        sections[2:2] = [run_check, run_discovery]
    if args.full:
        sections.append(run_full_plan)
    for section in sections:
        try:
            section(base)
        except Exception as exc:
            check(f"{section.__name__} crashed", False, f"{type(exc).__name__}: {exc}"[:200])

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
