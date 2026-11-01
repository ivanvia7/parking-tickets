import csv
import json
from collections import Counter
from pathlib import Path

import httpx
import pytest
import respx

from parking_tickets import cities, groups
from parking_tickets.portals import carto, socrata
from parking_tickets.schema import to_ticket

FIXTURES = Path(__file__).parent / "fixtures"
# A typo in groups.csv would make a new group nobody filters on; list them here.
KNOWN_GROUPS = {
    "street_cleaning", "meter", "time_limit", "permit", "no_parking",
    "no_stopping", "loading_zone", "bus_zone", "hydrant", "double_parking",
    "driveway", "sidewalk", "crosswalk", "disabled", "registration", "plates",
    "inspection", "bike_lane", "speed_camera", "red_light_camera", "transit_fare",
}  # fmt: skip


def csv_rows() -> list[dict]:
    with groups.GROUPS_FILE.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_groups_csv_uses_known_groups_and_cities():
    rows = csv_rows()
    assert {r["group"] for r in rows} <= KNOWN_GROUPS
    assert {r["city"] for r in rows} <= set(cities.slugs())


def test_groups_csv_lists_each_code_once():
    keys = Counter((r["city"], r["code"].strip()) for r in csv_rows())
    assert [k for k, n in keys.items() if n > 1] == []


def test_known_unknown_blank_and_padded_codes():
    assert groups.group_of("la", "80.69BS") == "street_cleaning"
    assert groups.group_of("la", " 80.69BS ") == "street_cleaning"
    assert groups.group_of("la", "NOT-A-CODE") == "other"
    assert groups.group_of("la", "") == "other"
    assert groups.group_of("la", None) == "other"
    assert groups.group_of("atlantis", "80.69BS") == "other"


def test_philadelphia_groups_by_description():
    city = cities.load("philadelphia")
    row = json.loads((FIXTURES / "philadelphia.json").read_text())[1]
    assert to_ticket(city, row).group == "meter"
    assert to_ticket(city, {**row, "violation_desc": None}).group == "other"


def test_la_fixture_rows_get_groups():
    city = cities.load("la")
    rows = json.loads((FIXTURES / "la.json").read_text())
    assert to_ticket(city, rows[0]).group == "street_cleaning"


def test_missing_groups_file_fails_loud(tmp_path, monkeypatch):
    monkeypatch.setattr(groups, "GROUPS_FILE", tmp_path / "groups.csv")
    groups.table.cache_clear()
    try:
        with pytest.raises(FileNotFoundError):
            groups.group_of("la", "80.69BS")
    finally:
        groups.table.cache_clear()


@respx.mock
def test_socrata_count_by_sums_both_nyc_datasets(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.MIN_GAP_SECONDS", 0)
    host = "https://data.cityofnewyork.us/resource"
    respx.get(f"{host}/m5vz-tzqv.json").mock(
        return_value=httpx.Response(
            200, json=[{"violation_code": "21", "n": "5"}, {"n": "1"}]
        )
    )
    respx.get(f"{host}/9mwx-gamw.json").mock(
        return_value=httpx.Response(200, json=[{"violation_code": "21", "n": "2"}])
    )
    city = cities.load("nyc")
    counts = socrata.count_by(city, "violation_code", "2025-06-01", "2025-06-30")
    assert counts == {"21": 7, None: 1}


@respx.mock
def test_carto_count_by_sends_group_by(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.MIN_GAP_SECONDS", 0)
    route = respx.get("https://phl.carto.com/api/v2/sql").mock(
        return_value=httpx.Response(200, json={"rows": [{"key": "SIDEWALK", "n": 3}]})
    )
    city = cities.load("philadelphia")
    counts = carto.count_by(city, "violation_desc", "2017-06-01", "2017-06-30")
    sql = route.calls[0].request.url.params["q"]
    assert counts == {"SIDEWALK": 3}
    assert "GROUP BY violation_desc" in sql and "< '2017-07-01'" in sql
