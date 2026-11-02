"""web/app.js reads times, groups, places, fines and datasets exactly like the package."""

import json
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from parking_tickets import cities, groups, schema
from parking_tickets.portals import socrata

ROOT = Path(__file__).parent.parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="needs node")
sys.path.insert(0, str(ROOT / "scripts"))
from build_web import web_city  # noqa: E402

# Reads {city, cases} on stdin, prints what the page makes of each case.
SCRIPT = """
import { readFileSync } from "node:fs";
import * as app from "%s";
const { city, cases } = JSON.parse(readFileSync(0, "utf8"));
console.log(JSON.stringify(cases.map(([name, ...args]) => app[name](city, ...args))));
"""

TIMES = ["904", "0904", "2359", "2400", "1260", "", "abc"]
NYC_TIMES = ["1008P", "1200A", "1200P", "0145A", "1300P", "0960A", "1008", ""]
OAKLAND_TIMES = ["10:41", "0:05", "23:59", "24:00", "10:60", "1041", "", "10:4"]
POINTS = [
    ("34.05", "-118.25"),
    ("0", "-118.25"),
    ("41.2", "-96.0"),
    ("34.05", ""),
    (None, None),
]


def run_page(city: dict, cases: list[list]) -> list:
    script = SCRIPT % (ROOT / "web" / "app.js").as_uri()
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        input=json.dumps({"city": city, "cases": cases}),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def test_times_match_schema() -> None:
    for slug, values in (("la", TIMES), ("nyc", NYC_TIMES), ("oakland", OAKLAND_TIMES)):
        city = web_city(slug)
        expected = [
            schema.TIME_FORMATS[city["time_format"]](v) if v else None for v in values
        ]
        assert run_page(city, [["clock", v] for v in values]) == expected


def test_groups_match_groups_csv() -> None:
    for slug in cities.slugs():
        city = web_city(slug)
        codes = [code for (owner, code) in groups.table() if owner == slug][:20]
        codes += ["NOT A CODE", "", None]
        expected = [groups.group_of(slug, code) for code in codes]
        assert run_page(city, [["groupOf", code] for code in codes]) == expected


def test_places_match_schema() -> None:
    city = web_city("la")
    expected = [list(schema.place(city, lat, lon)) for lat, lon in POINTS]
    assert run_page(city, [["place", lat, lon] for lat, lon in POINTS]) == expected


# Separate lat and lon columns (LA) and one GeoJSON point column (Oakland).
COORD_ROWS = {
    "la": [{"loc_lat": "34.05", "loc_long": "-118.25"}, {"loc_lat": "34.05"}, {}],
    "oakland": [
        {"the_geom": {"type": "Point", "coordinates": [-122.27, 37.8]}},
        {"the_geom": {"type": "Point", "coordinates": [165.99, -90]}},
        {"the_geom": None},
        {},
    ],
}


def test_coords_match_schema() -> None:
    for slug, rows in COORD_ROWS.items():
        city = web_city(slug)
        expected = [list(schema.coords(city, row)) for row in rows]
        assert run_page(city, [["coords", row] for row in rows]) == expected


def day_counts(first: str, counts: str) -> dict[str, int]:
    start = date.fromisoformat(first)
    return {
        (start + timedelta(days=offset)).isoformat(): int(n)
        for offset, n in enumerate(counts.split())
    }


# Live per-day counts read 2026-11-02; each city's newest days were still uploading.
NEWEST_DAYS = [
    # LA 10-29 and 10-30 hold 64% and 68% of their weekday.
    (
        "la",
        "2026-10-03",
        "2749 1806 6145 7198 7994 7561 1226 302 1344 1224 7093 6472 7221 6238 2888 1554 6737 7257 7300 8250 6973 696 1633 6980 7417 6557 4835 4741",
        "2026-10-28",
    ),
    # SF 10-28 holds 549 of about 5,000.
    (
        "sf",
        "2026-10-01",
        "4458 4302 2047 1159 4443 4838 4784 5207 4457 1993 984 1571 5184 5127 5345 4814 906 173 522 5150 4871 4659 4178 1193 889 3913 4126 549",
        "2026-10-27",
    ),
    # NYC 09-20 to 09-29 hold 3/4 of a day or less; Labor Day 09-07 is low.
    (
        "nyc",
        "2026-09-01",
        "40200 38295 45156 39973 28924 20637 20130 43793 38899 40571 31180 29319 14921 44834 47436 41071 47595 41810 32337 15778 22183 26528 21251 24387 18769 4939 4528 3159 2300",
        "2026-09-19",
    ),
    # Oakland's last week is complete; Fridays swing from 1,200 to 2,000.
    (
        "oakland",
        "2026-07-07",
        "1592 1570 1869 1664 1030 321 1354 1947 1493 1622 1983 1131 288 1214 1486 1148 1450 1217 619 316 1230 1826 1202 1345 1523",
        "2026-07-31",
    ),
]


def test_complete_day_skips_half_published_days() -> None:
    for slug, first, counts, newest in NEWEST_DAYS:
        city = web_city(slug)
        assert run_page(city, [["completeDay", day_counts(first, counts)]]) == [newest]


def test_complete_day_keeps_floor_for_small_cities() -> None:
    city = web_city("everett")  # full_day_tickets 20
    counts = {"2026-10-23": 32, "2026-10-24": 1, "2026-10-16": 11, "2026-10-09": 22}
    assert run_page(
        city, [["completeDay", counts], ["completeDay", {"2026-10-24": 1}]]
    ) == ["2026-10-23", None]


def test_nyc_fines_and_datasets_match() -> None:
    city = web_city("nyc")
    entry = {"manhattan_96th_st_below": "115", "all_other_areas": "65"}
    fines = [["tableFine", entry, precinct] for precinct in ("1", "22", "75")]
    fines.append(
        ["tableFine", {"all_other_areas": "65"}, "1"]
    )  # code without a zone amount
    expected_fines = [
        schema.number(
            schema.fine_from_table(city, case[1], {"violation_precinct": case[2]})
        )
        for case in fines
    ]
    spans = [
        ("2025-06-30", "2025-06-30"),
        ("2025-07-01", "2025-07-01"),
        ("2026-09-29", "2026-09-29"),
        ("2025-06-01", "2026-08-31"),
    ]
    expected_sets = [socrata.dataset_ids(city, *span) for span in spans]
    got = run_page(city, fines + [["datasetsFor", *span] for span in spans])
    assert got == expected_fines + expected_sets
