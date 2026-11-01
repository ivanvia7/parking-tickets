import json
from pathlib import Path

import httpx
import respx

from parking_tickets import cities
from parking_tickets.portals import carto
from parking_tickets.schema import to_ticket

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "philadelphia.json").read_text()
)
URL = "https://phl.carto.com/api/v2/sql"


def test_day_filter_spans_one_day():
    assert (
        carto.day_filter("d", "2017-12-31") == "d >= '2017-12-31' AND d < '2018-01-01'"
    )


@respx.mock
def test_read_day_maps_philadelphia_rows(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.MIN_GAP_SECONDS", 0)
    respx.get(URL).mock(return_value=httpx.Response(200, json={"rows": FIXTURE}))
    city = cities.load("philadelphia")
    tickets = [to_ticket(city, r) for r in carto.read_day(city, "2017-06-06")]
    assert len(tickets) == len(FIXTURE)
    assert all(t.issued_at.startswith("2017-06-06T") for t in tickets)
    assert all(isinstance(t.source_id, str) for t in tickets)
