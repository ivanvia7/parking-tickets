"""web/app.js reads times, groups, places, fines and datasets exactly like the package."""

import json
import shutil
import subprocess
import sys
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
    days = ["2025-06-30", "2025-07-01", "2026-09-29"]
    expected_sets = [socrata.dataset_ids(city, day) for day in days]
    got = run_page(city, fines + [["datasetsFor", day, day] for day in days])
    assert got == expected_fines + expected_sets
