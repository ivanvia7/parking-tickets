import json
import subprocess
from pathlib import Path

import httpx
import pytest
import respx

from parking_tickets import cities
from parking_tickets.check import check_city, city_columns

FIXTURES = Path(__file__).parent / "fixtures"
LA_URL = "https://data.lacity.org/resource/4f5p-udkv.json"
PHL_URL = "https://phl.carto.com/api/v2/sql"


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.MIN_GAP_SECONDS", 0)


def test_city_columns_lists_joined_and_zone_columns_once():
    names = city_columns(cities.load("nyc"))
    assert {"house_number", "street_name", "violation_precinct"} <= set(names)
    assert len(names) == len(set(names))


@respx.mock
def test_live_rows_pass():
    rows = json.loads((FIXTURES / "la.json").read_text())
    route = respx.get(LA_URL).mock(return_value=httpx.Response(200, json=rows))
    assert check_city("la") == (len(rows), 0)
    params = route.calls[0].request.url.params
    assert "violation_code" in params["$select"] and params["$limit"] == "100"


@respx.mock
def test_missing_column_names_city_and_dataset():
    body = {"message": "No such column: violation_kode"}
    respx.get(LA_URL).mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(RuntimeError, match=r"la \(data.lacity.org 4f5p-udkv\).*kode"):
        check_city("la")


@respx.mock
def test_no_rows_fails():
    respx.get(PHL_URL).mock(return_value=httpx.Response(200, json={"rows": []}))
    with pytest.raises(RuntimeError, match="no rows"):
        check_city("philadelphia")


@respx.mock
def test_all_rows_unreadable_fails():
    rows = [{"anon_ticket_number": 1, "issue_datetime": None}]
    respx.get(PHL_URL).mock(return_value=httpx.Response(200, json={"rows": rows}))
    with pytest.raises(RuntimeError, match="none of 1 rows readable"):
        check_city("philadelphia")


def test_cli_unknown_city_exits_2():
    result = subprocess.run(
        ["parking-tickets", "check-city", "atlantis"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "unknown city atlantis" in result.stderr


def test_cli_lists_cities():
    result = subprocess.run(
        ["parking-tickets", "cities"], capture_output=True, text=True, check=True
    )
    assert result.stdout.split() == cities.slugs()
