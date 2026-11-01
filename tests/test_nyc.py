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
    for row, ticket in zip(ROWS, tickets):
        midtown = row.get("violation_precinct") in city["fine_lookup"]["zone_values"]
        assert ticket.fine_usd == (65.0 if midtown else 35.0)
        assert ticket.location and ticket.issued_at.startswith("2025-06-03")
