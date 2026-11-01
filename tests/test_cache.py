import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import respx

from parking_tickets import api, cache

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "la.json").read_text())
URL = "https://data.lacity.org/resource/4f5p-udkv.json"


@respx.mock
def test_second_fetch_makes_no_requests(tmp_path, monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.MIN_GAP_SECONDS", 0)
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    conn = cache.open_cache(tmp_path / "c.db")
    day = date(2025, 6, 3)
    assert api.fetch(conn, "la", day, day) == len(FIXTURE)
    assert api.fetch(conn, "la", day, day) == 0
    assert route.call_count == 1


@respx.mock
def test_recent_day_is_read_again(tmp_path, monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.MIN_GAP_SECONDS", 0)
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=[]))
    conn = cache.open_cache(tmp_path / "c.db")
    yesterday = date.today() - timedelta(days=1)
    api.fetch(conn, "la", yesterday, yesterday)
    api.fetch(conn, "la", yesterday, yesterday)
    assert route.call_count == 2
