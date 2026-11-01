import json
from pathlib import Path

from parking_tickets import cities
from parking_tickets.portals.socrata import dataset_ids
from parking_tickets.schema import hhmmp_time, to_ticket

ROWS = json.loads((Path(__file__).parent / "fixtures" / "nyc.json").read_text())


def test_hhmmp_time():
    assert hhmmp_time("1008P") == "22:08"
    assert hhmmp_time("1208A") == "00:08"
    assert hhmmp_time("1208P") == "12:08"
    assert hhmmp_time("0000") is None


def test_day_reads_its_fiscal_year_and_the_next():
    city = cities.load("nyc")
    assert dataset_ids(city, "2025-06-03") == ["m5vz-tzqv", "9mwx-gamw"]
    assert dataset_ids(city, "2025-07-01") == ["9mwx-gamw", "pvqr-7yc4"]
    assert dataset_ids(city, "2026-08-01") == ["pvqr-7yc4"]


def test_fine_comes_from_code_table_by_zone():
    city = cities.load("nyc")
    table = {
        row["violation_code"]: {
            "all_other_areas": "35",
            "manhattan_96th_st_below": "65",
        }
        for row in ROWS
    }
    tickets = [to_ticket(city, row, table) for row in ROWS]
    for row, ticket in zip(ROWS, tickets, strict=True):
        midtown = row.get("violation_precinct") in city["fine_lookup"]["zone_values"]
        assert ticket.fine_usd == (65.0 if midtown else 35.0)
        assert ticket.location and ticket.issued_at.startswith("2025-06-03")


def test_manhattan_zone_pays_the_higher_fine():
    city = cities.load("nyc")
    table = {"14": {"all_other_areas": "95", "manhattan_96th_st_below": "115"}}
    row = {**ROWS[0], "violation_code": "14", "violation_precinct": "14"}
    assert to_ticket(city, row, table).fine_usd == 115.0
    row["violation_precinct"] = "109"
    assert to_ticket(city, row, table).fine_usd == 95.0


def test_day_without_a_listed_dataset_fails():
    try:
        dataset_ids(cities.load("nyc"), "2012-01-01")
    except ValueError as error:
        assert "2012" in str(error)
    else:
        raise AssertionError("expected ValueError")
