"""Offline tests for the opening-hours check, plan parsing, storage and exports."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from voyagent import exports, hours, storage  # noqa: E402
from voyagent.plan_text import split_days  # noqa: E402

DATES = "07 December 2026 - 09 December 2026"
PLAN = """Intro about Tunis.

## Getting around
- Taxis are cheap.

## Day 1: Monday 07 December 2026
| Time | Area / Activity | Travel time |
|---|---|---|
| Morning | Bardo Museum – mosaics | 15 min |
| Evening | Avenue Habib Bourguiba | 10 min |

## Day 2: Tuesday 08 December 2026
### Morning
- Carthage ruins, then the Carthage Museum

## Day 3: Wednesday 09 December 2026
- Sidi Bou Said

## Budget
| Item | TND |
|---|---|
| Total | 358 |
"""


@pytest.mark.parametrize(
    ("spec", "closed"),
    [
        ("Tu-Su 09:00-17:00", ["Monday"]),
        ("Mo-Fr 08:00-18:00; Sa 09:00-13:00", ["Sunday"]),
        ("24/7", []),
        ("09:00-18:00", []),
        ("Mo off; Tu-Su 10:00-18:00", ["Monday"]),
        ("Sa-Mo 10:00-12:00", ["Tuesday", "Wednesday", "Thursday", "Friday"]),
        ("Mo-Th,Sa,Su 08:30-17:00; PH off", ["Friday"]),
    ],
)
def test_osm_closed_days(spec, closed):
    assert hours.osm_closed_days(spec) == closed


@pytest.mark.parametrize("spec", ["", "Apr-Oct Tu-Su 10:00-18:00", "Mo-Su 09:00-17:00; Fr 12:00-14:00 off"])
def test_osm_closed_days_unknown(spec):
    # Anything we can't read fully is "not verified", never a guess.
    assert hours.osm_closed_days(spec) is None


def test_split_days_dates_items_and_last_day_boundary():
    days = split_days(PLAN, DATES)
    assert [(d.number, d.weekday) for d in days] == [(1, "Monday"), (2, "Tuesday"), (3, "Wednesday")]
    assert days[0].items[0].startswith("Morning: Bardo Museum")
    assert "Carthage" in days[1].text  # sub-headings stay inside their day
    assert "Budget" not in days[2].text and "358" not in days[2].text


def test_conflict_found_and_warning_placed():
    days = split_days(PLAN, DATES)
    check = hours.PlaceCheck(name="Bardo National Museum", closed_days=["Monday"], status="ok")
    conflicts = hours._conflicts(days, [check])
    assert [(c.name, d.number) for c, d in conflicts] == [("Bardo National Museum", 1)]
    warned = hours._warn(PLAN, conflicts)
    day1 = warned.split("## Day 2")[0]
    assert "closed on Mondays" in day1


def test_check_plan_moves_closed_visit(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(hours, "_scheduled_places", lambda days, city: ["Bardo Museum"])

    def fake_lookup(checks, city):
        for c in checks:
            c.closed_days, c.status, c.source = ["Monday"], "ok", "OpenStreetMap"

    monkeypatch.setattr(hours, "_lookup", fake_lookup)
    moved = PLAN.replace("| Morning | Bardo Museum – mosaics | 15 min |", "| Morning | Medina walk | 0 min |").replace(
        "- Sidi Bou Said", "- Sidi Bou Said\n- Bardo Museum – mosaics"
    )
    monkeypatch.setattr(hours, "_fix", lambda plan, conflicts, dates: moved)
    plan, checks = hours.check_plan(PLAN, "Tunis", DATES)
    assert plan == moved
    assert checks[0]["status"] == "moved" and checks[0]["days"] == [3]


def test_check_plan_never_raises(monkeypatch):
    def boom(*_args):
        raise RuntimeError("model down")

    monkeypatch.setattr(hours, "_scheduled_places", boom)
    assert hours.check_plan(PLAN, "Tunis", DATES) == (PLAN, [])


def test_chosen_city():
    assert hours.chosen_city("Three days in Tunis. Tunis medina...", "Djerba, Tunis") == "Tunis"


def test_storage_local_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    assert not storage.is_remote()
    storage.save("plans", "abc123def456", {"id": "abc123def456", "result": "Musée"})
    assert storage.load("plans", "abc123def456")["result"] == "Musée"
    assert storage.load("plans", "000000000000") is None
    with pytest.raises(ValueError):
        storage.save("plans", "../evil", {})


def test_storage_reads_remote_when_local_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example.upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")
    calls = []

    def fake_redis(*command):
        calls.append(command[0])
        return '{"id": "abc"}' if command[0] == "GET" else "OK"

    monkeypatch.setattr(storage, "_redis", fake_redis)
    assert storage.load("plans", "abc") == {"id": "abc"}
    assert (tmp_path / "plans" / "abc.json").exists()  # cached locally after a remote read
    assert calls == ["GET"]


def test_ics_has_one_event_per_day():
    ics = exports.to_ics({"id": "abc", "result": PLAN, "request": {"cities": "Tunis", "travel_dates": DATES}})
    assert ics.count("BEGIN:VEVENT") == 3
    assert "DTSTART;VALUE=DATE:20261207" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))


def test_complete_json_retries_empty_then_falls_back(monkeypatch):
    from types import SimpleNamespace

    from voyagent import config, llm

    monkeypatch.setattr(config, "helper_model", lambda: "gemini/flash")
    monkeypatch.setattr(config, "litellm_model", lambda: "groq/main")
    calls = []

    def fake_complete(**request):
        calls.append(request["model"])
        content = '{"places": ["Bardo"]}' if request["model"] == "groq/main" else ""
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    monkeypatch.setattr(llm, "complete", fake_complete)
    assert llm.complete_json("prompt") == {"places": ["Bardo"]}
    assert calls == ["gemini/flash", "gemini/flash", "groq/main"]


def test_closed_mention_is_not_a_visit():
    plan = PLAN.replace(
        "| Morning | Bardo Museum – mosaics | 15 min |",
        "| Morning | Medina walk, instead of the closed Bardo Museum | 0 min |",
    )
    days = split_days(plan, DATES)
    check = hours.PlaceCheck(name="Bardo National Museum", closed_days=["Monday"], status="ok")
    assert hours._conflicts(days, [check]) == []
