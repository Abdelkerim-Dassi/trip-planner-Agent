"""Offline tests for the itinerary check: reading, map matching, findings."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from voyagent import hours, places, review, storage  # noqa: E402
from voyagent.places import Place  # noqa: E402
from voyagent.plan_text import split_days  # noqa: E402


def place(name, lat, lon, kind="attraction", category="tourism", osm_type="museum",
          opening_hours="", locality="Tunis", country="tn"):
    return Place(
        name=name, display_name=name, lat=lat, lon=lon, country_code=country, kind=kind,
        osm_url=f"https://www.openstreetmap.org/node/{abs(hash(name)) % 10**6}",
        category=category, osm_type=osm_type, opening_hours=opening_hours, locality=locality,
    )


TUNIS = place("Tunis", 36.80, 10.18, kind="city", category="place", osm_type="city")
KAIROUAN = place("Kairouan", 35.67, 10.10, kind="city", category="place", osm_type="city",
                 locality="Kairouan")
ON_MAP = {
    "Bardo National Museum": place("Bardo National Museum", 36.81, 10.13, opening_hours="Tu-Su 09:30-16:30"),
    "Medina of Tunis": place("Medina of Tunis", 36.80, 10.17, category="boundary", osm_type="protected_area"),
    "Great Mosque of Kairouan": place("Great Mosque", 35.68, 10.10, category="amenity",
                                      osm_type="place_of_worship", locality="Kairouan"),
    # The restaurant exists, but in Sidi Bou Said, not Kairouan.
    "Dar Zarrouk": place("Dar Zarrouk", 36.87, 10.35, category="amenity", osm_type="restaurant"),
    "El Jem Amphitheatre": place("El Jem", 35.30, 10.71, locality="Mahdia"),
    "Sousse Medina": place("Sousse Medina", 35.83, 10.64, category="boundary", osm_type="protected_area",
                           locality="Sousse"),
}
EXTRACTED = {
    "destination": "Tunis, Tunisia",
    "start_date": "",
    "days": [
        {"day": 1, "city": "Tunis", "stops": [
            {"name": "Medina of Tunis", "kind": "area"},
            {"name": "Bardo National Museum", "kind": "sight"},
            {"name": "Crystal Lagoon Viewpoint", "kind": "sight"},
        ]},
        {"day": 2, "city": "Kairouan", "stops": [
            {"name": "Great Mosque of Kairouan", "kind": "sight"},
            {"name": "Dar Zarrouk", "kind": "food"},
            {"name": "El Jem Amphitheatre", "kind": "sight"},
            {"name": "Sousse Medina", "kind": "area"},
        ]},
    ],
}
TEXT = "Day 1: Medina of Tunis, Bardo National Museum... Day 2: Kairouan, El Jem, Sousse."


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """No model, no map server, no web search: canned answers instead."""
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(review, "_extract", lambda text, destination: EXTRACTED)
    cities = {"Tunis": TUNIS, "Kairouan": KAIROUAN, "Tunis, Tunisia": TUNIS}
    monkeypatch.setattr(review, "geocode", lambda query, *a, **k: cities.get(query) or ON_MAP.get(query))
    monkeypatch.setattr(review, "verify_place", lambda name, near="": ON_MAP.get(name))
    monkeypatch.setattr(hours, "verify_place", lambda name, near="": ON_MAP.get(name))
    monkeypatch.setattr(hours, "_from_snippets", lambda pending, city, model=None: set())
    monkeypatch.setattr(review, "search", lambda query: [])  # the web knows nothing
    monkeypatch.setattr(review, "ramadan_days", lambda start, end: [])


def issue(report, kind):
    return [i for i in report["issues"] if i["kind"] == kind]


def test_three_column_table_keeps_the_activity():
    plan = (
        "## Day 1: Monday 07 December 2026\n"
        "| Time | Area | Activity |\n|---|---|---|\n"
        "| Morning | Le Bardo | Bardo National Museum: the mosaics |\n"
    )
    day = split_days(plan, "07 December 2026 - 07 December 2026")[0]
    assert "Bardo National Museum" in day.items[0]


def test_check_finds_closed_day_fake_place_wrong_city_and_long_day(offline):
    report = review.run(TEXT, start=date(2026, 12, 14))  # a Monday
    status = {s["name"]: s["status"] for s in report["stops"]}

    closed = issue(report, "closed")
    assert [i["stop"] for i in closed] == ["Bardo National Museum"] and closed[0]["level"] == "problem"
    assert "Monday" in closed[0]["title"]

    assert status["Crystal Lagoon Viewpoint"] == "no_trace"
    assert issue(report, "no_trace")[0]["level"] == "problem"

    # A restaurant 130+ km from the day's town is a problem; a sight that far is a warning.
    far = {i["stop"]: i["level"] for i in issue(report, "far")}
    assert status["Dar Zarrouk"] == "far" and far["Dar Zarrouk"] == "problem"
    assert far["El Jem Amphitheatre"] == "warning"

    long_day = issue(report, "long_day")
    assert [i["day"] for i in long_day] == [2]
    assert "Dar Zarrouk" not in long_day[0]["detail"]  # the misplaced lunch isn't part of the route

    summary = report["summary"]
    assert summary["places"] == 7 and summary["confirmed"] == 4 and summary["far"] == 2
    assert summary["no_trace"] == 1 and summary["hours_checked"] == 1
    assert summary["problems"] == 3
    assert "Bardo National Museum is closed on Mondays" in report["fix_prompt"]


def test_without_dates_closing_days_are_notes_not_problems(offline):
    report = review.run(TEXT)
    assert not issue(report, "closed")
    assert [i["stop"] for i in issue(report, "closing_day")] == ["Bardo National Museum"]
    assert issue(report, "no_dates")


def test_place_missing_from_map_but_known_online_is_not_a_problem(offline, monkeypatch):
    hit = {"title": "Crystal Lagoon Viewpoint - Tripadvisor", "snippet": "", "link": "https://example.com/a"}
    monkeypatch.setattr(review, "search", lambda query: [hit, hit])
    report = review.run(TEXT, start=date(2026, 12, 15))
    stop = next(s for s in report["stops"] if s["name"] == "Crystal Lagoon Viewpoint")
    assert stop["status"] == "web" and stop["web_source"] == "https://example.com/a"
    assert not issue(report, "no_trace") and issue(report, "web_only")[0]["level"] == "note"


def test_same_name_wrong_kind_of_business_is_not_a_match(offline, monkeypatch):
    wine_shop = place("Dar Zarrouk", 35.70, 10.12, category="shop", osm_type="wine", locality="Kairouan")
    monkeypatch.setattr(review, "verify_place", lambda name, near="": wine_shop if name == "Dar Zarrouk" else ON_MAP.get(name))
    monkeypatch.setattr(review, "geocode", lambda query, *a, **k: {"Tunis": TUNIS, "Kairouan": KAIROUAN,
                                                                  "Tunis, Tunisia": TUNIS}.get(query) or ON_MAP.get(query))
    report = review.run(TEXT, start=date(2026, 12, 15))
    stop = next(s for s in report["stops"] if s["name"] == "Dar Zarrouk")
    assert stop["status"] == "far" and stop["distance_km"] > 100  # the real restaurant, not the shop


def test_friday_and_halal_notes(offline):
    report = review.run(TEXT, start=date(2026, 12, 17), halal=True)  # Thursday, then Friday
    friday = issue(report, "friday")
    assert [i["day"] for i in friday] == [2] and "Great Mosque of Kairouan" in friday[0]["detail"]


def test_long_itineraries_are_trimmed_fairly():
    data = {"days": [
        {"day": d, "city": "Rome", "stops": [{"name": f"Place {d}-{n}", "kind": "sight"} for n in range(8)]}
        for d in range(1, 8)
    ]}
    days, stops, trimmed = review._parse_days(data, "Rome", max_stops=28)
    assert trimmed and len(stops) == 28
    assert {s.day for s in stops} == set(range(1, 8))  # every day still checked
    assert max(sum(s.day == d for s in stops) for d in range(1, 8)) == 4


def test_unreadable_text_gives_a_message_for_the_user(offline, monkeypatch):
    with pytest.raises(review.ReviewError):
        review.run("too short")
    monkeypatch.setattr(review, "_extract", lambda text, destination: {"days": []})
    with pytest.raises(review.ReviewError):
        review.run(TEXT)


def test_check_plan_never_raises_and_moves_closed_visit(offline, monkeypatch):
    dates = "14 December 2026 - 15 December 2026"
    plan = (
        "Two days.\n\n## Day 1: Monday 14 December 2026\n- Medina of Tunis\n- Bardo National Museum\n\n"
        "## Day 2: Tuesday 15 December 2026\n- Great Mosque of Kairouan\n" + "Filler. " * 40
    )
    moved = plan.replace("- Bardo National Museum\n", "").replace(
        "- Great Mosque of Kairouan\n", "- Great Mosque of Kairouan\n- Bardo National Museum\n"
    )
    monkeypatch.setattr(hours, "_fix", lambda p, conflicts, d: moved)
    fixed, report = review.check_plan(plan, "Tunis", dates)
    assert fixed == moved
    bardo = next(s for s in report["stops"] if s["name"] == "Bardo National Museum")
    assert bardo["day"] == 2 and bardo["moved_from"] == 1
    assert not issue(report, "closed") and issue(report, "moved")
    assert review.legacy_checks(report)[0]["status"] == "moved"

    # When the edit replaces the visit instead of moving it, the report drops it too.
    replaced = plan.replace("- Bardo National Museum\n", "- Dar Ben Abdallah\n")
    monkeypatch.setattr(hours, "_fix", lambda p, conflicts, d: replaced)
    fixed, report = review.check_plan(plan, "Tunis", dates)
    assert fixed == replaced
    assert "Bardo National Museum" not in [s["name"] for s in report["stops"]]
    assert not issue(report, "closed") and "replaced" in report["notes"][0]

    monkeypatch.setattr(review, "_extract", lambda *a: (_ for _ in ()).throw(RuntimeError("model down")))
    assert review.check_plan(plan, "Tunis", dates) == (plan, None)


def test_geocode_prefers_a_match_near_the_city(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(places, "_memory", {})
    hits = [
        {"name": "Medina", "lat": "35.83", "lon": "10.64", "osm_type": "way", "osm_id": 1,
         "address": {"city": "Sousse", "country_code": "tn"}},
        {"name": "Medina of Tunis", "lat": "36.80", "lon": "10.17", "osm_type": "way", "osm_id": 2,
         "address": {"city": "Tunis", "country_code": "tn"}},
    ]
    calls = []

    def fake_get(params):
        calls.append(params)
        return hits

    monkeypatch.setattr(places, "_throttled_get", fake_get)
    assert places.geocode("Medina", "tn").locality == "Sousse"  # no preference: top match
    near = places.geocode("Medina", "tn", (36.80, 10.18))
    assert near.locality == "Tunis" and "viewbox" in calls[-1]
    assert places.geocode("Medina", "tn", (36.80, 10.18)) is near and len(calls) == 2  # cached

    # A failed request is "unverified" now and asked again next time, not cached as missing.
    monkeypatch.setattr(places, "_throttled_get", lambda params: None)
    assert places.geocode("Nowhere", "tn") is None
    monkeypatch.setattr(places, "_throttled_get", lambda params: hits[:1])
    assert places.geocode("Nowhere", "tn") is not None
