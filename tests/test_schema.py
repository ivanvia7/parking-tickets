import json
from pathlib import Path

from parking_tickets import cities
from parking_tickets.schema import COLUMNS, hmm_time, to_ticket

FIXTURES = Path(__file__).parent / "fixtures"


def test_hmm_time_pads_short_values():
    assert hmm_time("904") == "09:04"
    assert hmm_time("0") == "00:00"
    assert hmm_time("2358") == "23:58"
    assert hmm_time("2400") is None
    assert hmm_time("9999") is None


def test_la_rows_map_to_schema():
    city = cities.load("la")
    rows = json.loads((FIXTURES / "la.json").read_text())
    tickets = [to_ticket(city, row) for row in rows]
    assert all(t.city == "la" and t.fine_usd is not None for t in tickets)
    assert all(t.issued_at.startswith("2025-06-03T") for t in tickets)
    assert len(COLUMNS) == 11


def test_unknown_city_names_known_ones():
    try:
        cities.load("atlantis")
    except ValueError as error:
        assert "la" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_sf_rows_map_to_schema():
    city = cities.load("sf")
    rows = json.loads((FIXTURES / "sf.json").read_text())
    tickets = [to_ticket(city, row) for row in rows]
    assert all(t.fine_usd is not None for t in tickets)
    assert all(t.issued_at.startswith("2025-06-03T") for t in tickets)


def test_blank_time_keeps_the_date_only():
    city = cities.load("la")
    row = {**json.loads((FIXTURES / "la.json").read_text())[0], "issue_time": ""}
    assert to_ticket(city, row).issued_at == "2025-06-03"


def test_blank_date_is_an_unreadable_row():
    city = cities.load("la")
    row = {**json.loads((FIXTURES / "la.json").read_text())[0], "issue_date": ""}
    try:
        to_ticket(city, row)
    except ValueError as error:
        assert "issue_date" in str(error)
    else:
        raise AssertionError("expected ValueError")
