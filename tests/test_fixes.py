import json
import sqlite3
import subprocess
from pathlib import Path

import httpx
import pytest
import respx

from parking_tickets import api, cities
from parking_tickets.check import check_city
from parking_tickets.portals import socrata
from parking_tickets.schema import to_ticket

FIXTURES = Path(__file__).parent / "fixtures"
LA = json.loads((FIXTURES / "la.json").read_text())
NYC = json.loads((FIXTURES / "nyc.json").read_text())


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.MIN_GAP_SECONDS", 0)


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        ("46.5653163", "-66.4619164"),
        ("22.9867569", "87.8549755"),
        ("34.05", ""),
        ("0", "0"),
    ],
)
def test_point_outside_city_or_half_missing_is_dropped(lat, lon):
    row = {**LA[0], "loc_lat": lat, "loc_long": lon}
    ticket = to_ticket(cities.load("la"), row)
    assert (ticket.lat, ticket.lon) == (None, None)


def test_point_inside_city_is_kept():
    row = {**LA[0], "loc_lat": "34.05", "loc_long": "-118.25"}
    ticket = to_ticket(cities.load("la"), row)
    assert (ticket.lat, ticket.lon) == (34.05, -118.25)


def test_nyc_text_comes_from_code_table_and_blank_amount_is_no_fine():
    city = cities.load("nyc")
    row = {**NYC[0], "violation_code": "21", "violation_precinct": "109"}
    table = {"21": {"definition": "NO PARKING-STREET CLEANING"}}
    ticket = to_ticket(city, row, table)
    assert ticket.violation_text == "NO PARKING-STREET CLEANING"
    assert ticket.fine_usd is None and ticket.group == "street_cleaning"
    unknown = to_ticket(city, {**row, "violation_code": "0"}, table)
    assert unknown.violation_text is None and unknown.group == "other"


@respx.mock
def test_html_instead_of_json_names_the_url():
    url = "https://data.lacity.org/resource/4f5p-udkv.json"
    respx.get(url).mock(return_value=httpx.Response(200, text="<html>down</html>"))
    with pytest.raises(RuntimeError, match=r"not JSON from https://data.lacity.org"):
        socrata.count("data.lacity.org", "4f5p-udkv", "1=1")


def test_check_city_names_city_when_fiscal_year_is_missing(monkeypatch):
    nyc = cities.load("nyc")
    monkeypatch.setattr(
        cities, "load", lambda slug: {**nyc, "datasets_by_fiscal_year": {}}
    )
    with pytest.raises(RuntimeError, match=r"nyc .*no dataset listed for fiscal year"):
        check_city("nyc")


def test_out_into_missing_folder_fails_before_download(tmp_path):
    result = subprocess.run(
        ["parking-tickets", "fetch", "--city", "la", "--since", "2025-06-03",
         "--until", "2025-06-03", "--cache", str(tmp_path / "c.db"),
         "--out", str(tmp_path / "nope" / "t.csv")],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 2 and "does not exist" in result.stderr


@respx.mock
def test_load_closes_its_cache(tmp_path, monkeypatch):
    respx.get("https://data.lacity.org/resource/4f5p-udkv.json").mock(
        return_value=httpx.Response(200, json=LA)
    )
    opened: list[sqlite3.Connection] = []
    real_open = api.cache.open_cache
    monkeypatch.setattr(
        api.cache,
        "open_cache",
        lambda path: opened.append(real_open(path)) or opened[-1],
    )
    api.load("la", "2025-06-03", "2025-06-03", cache_path=tmp_path / "c.db")
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


@respx.mock
def test_timeout_after_every_try_names_the_url(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.RETRY_SECONDS", 0)
    url = "https://data.lacity.org/resource/4f5p-udkv.json"
    route = respx.get(url).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(
        RuntimeError, match=r"ReadTimeout.*data.lacity.org.*after 3 tries"
    ):
        socrata.count("data.lacity.org", "4f5p-udkv", "1=1")
    assert route.call_count == 3


def test_cli_turns_portal_errors_into_one_line(monkeypatch, capsys):
    from parking_tickets import cli

    def broken(*args):
        raise RuntimeError("nyc 2025-06-03: ReadTimeout from https://x after 3 tries")

    monkeypatch.setattr(cli.api, "fetch", broken)
    monkeypatch.setattr(
        "sys.argv",
        ["parking-tickets", "fetch", "--city", "nyc", "--since", "2025-06-03",
         "--until", "2025-06-03"],
    )  # fmt: skip
    with pytest.raises(SystemExit, match=r"^error: nyc 2025-06-03: ReadTimeout"):
        cli.main()
