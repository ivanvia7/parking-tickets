import importlib.util
from datetime import date
from pathlib import Path

import httpx
import respx

spec = importlib.util.spec_from_file_location(
    "spot_check", Path(__file__).parent.parent / "scripts" / "spot_check.py"
)
assert spec and spec.loader
spot_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spot_check)

LA_ROW = {
    "ticket_number": "4597755444",
    "issue_date": "2025-01-30T00:00:00.000",
    "fine_amount": "63",
    "violation_code": "88.13B+",
    "location": "2200 PURDUE AV",
}
TICKET = {
    "source_id": "4597755444",
    "issued_at": "2025-01-30T13:11:00",
    "fine_usd": 63.0,
    "violation_code": "88.13B+",
    "violation_text": "METER EXP.",
    "location": "2200 PURDUE AV",
}


@respx.mock
def test_matching_ticket_has_no_mismatch_and_a_wrong_fine_is_named():
    respx.get(url__startswith="https://data.lacity.org/").mock(
        return_value=httpx.Response(200, json=[LA_ROW])
    )
    day = date(2025, 1, 30)
    assert spot_check.mismatches("la", TICKET, day) == []
    wrong = {**TICKET, "fine_usd": 68.0}
    assert spot_check.mismatches("la", wrong, day) == [("fine", 68.0, 63.0)]


@respx.mock
def test_missing_portal_row_is_reported():
    respx.get(url__startswith="https://data.lacity.org/").mock(
        return_value=httpx.Response(200, json=[])
    )
    got = spot_check.mismatches("la", TICKET, date(2025, 1, 30))
    assert got == [("city", "4597755444", "0 portal rows")]


NYC_ROW = {
    "summons_number": "5700983370",
    "issue_date": "2024-10-27T00:00:00.000",
    "violation_code": "15",
    "street_name": "EB W 207th St @ Sher",
}
NYC_TICKET = {
    "source_id": "5700983370",
    "issued_at": "2024-10-27T20:44:00",
    "fine_usd": None,
    "violation_code": "15",
    "violation_text": "MTA CAMERA DOUBLE PARKING",
    "location": "EB W 207th St @ Sher",
}


@respx.mock
def test_nyc_fine_comes_from_the_city_ticket_record():
    # The fiscal-year dataset has no fine; nc67-uf89 holds what the city charged.
    respx.get(url__regex=r"/resource/m5vz-tzqv\.json").mock(
        return_value=httpx.Response(200, json=[NYC_ROW])
    )
    respx.get(url__regex=r"/resource/nc67-uf89\.json").mock(
        return_value=httpx.Response(200, json=[{"fine_amount": "50"}])
    )
    day = date(2024, 10, 27)
    assert spot_check.mismatches("nyc", {**NYC_TICKET, "fine_usd": 50.0}, day) == []
    assert spot_check.mismatches("nyc", {**NYC_TICKET, "fine_usd": 115.0}, day) == [
        ("fine", 115.0, 50.0)
    ]
    # An empty fine where the city has one is reported apart, not passed.
    assert spot_check.mismatches("nyc", NYC_TICKET, day) == [("blank fine", None, 50.0)]
