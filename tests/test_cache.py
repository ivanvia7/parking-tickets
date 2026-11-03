import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from parking_tickets import api, cache
from parking_tickets.portals.http import get_json, retry_delay

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "la.json").read_text())
URL = "https://data.lacity.org/resource/4f5p-udkv.json"


@respx.mock
def test_second_fetch_makes_no_requests(tmp_path):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    conn = cache.open_cache(tmp_path / "c.db")
    day = date(2025, 6, 3)
    assert api.fetch(conn, "la", day, day) == (len(FIXTURE), [])
    assert api.fetch(conn, "la", day, day) == (0, [])
    assert route.call_count == 1


@respx.mock
def test_recent_day_is_read_again(tmp_path):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=[]))
    conn = cache.open_cache(tmp_path / "c.db")
    yesterday = date.today() - timedelta(days=1)
    api.fetch(conn, "la", yesterday, yesterday)
    api.fetch(conn, "la", yesterday, yesterday)
    assert route.call_count == 2


@respx.mock
def test_bad_row_is_skipped_and_counted(tmp_path):
    bad = {**FIXTURE[0], "ticket_number": "bad-1", "fine_amount": "n/a"}
    respx.get(URL).mock(return_value=httpx.Response(200, json=[*FIXTURE, bad]))
    conn = cache.open_cache(tmp_path / "c.db")
    day = date(2025, 6, 3)
    rows, skipped = api.fetch(conn, "la", day, day)
    assert rows == len(FIXTURE)
    assert len(skipped) == 1
    assert skipped[0].startswith(
        "ValueError(\"could not convert string to float: 'n/a'"
    )
    old = date(2020, 1, 6)
    api.fetch(conn, "la", old, old)
    assert not cache.is_fetched(conn, "la", "2020-01-06")


@respx.mock
def test_reread_day_drops_tickets_the_city_removed(tmp_path):
    yesterday = date.today() - timedelta(days=1)
    rows = [{**r, "issue_date": f"{yesterday}T00:00:00.000"} for r in FIXTURE]
    respx.get(URL).mock(
        side_effect=[httpx.Response(200, json=rows), httpx.Response(200, json=rows[:1])]
    )
    conn = cache.open_cache(tmp_path / "c.db")
    api.fetch(conn, "la", yesterday, yesterday)
    api.fetch(conn, "la", yesterday, yesterday)
    assert conn.execute("SELECT count(*) FROM tickets").fetchone()[0] == 1


@respx.mock
def test_timeout_is_retried(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.RETRY_SECONDS", 0)
    route = respx.get(URL).mock(
        side_effect=[
            httpx.ReadTimeout("slow"),
            httpx.Response(200, json=[{"count": "2"}]),
        ]
    )
    assert get_json(URL, {}, {}) == [{"count": "2"}]
    assert route.call_count == 2


@respx.mock
def test_busy_portal_is_retried(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.RETRY_SECONDS", 0)
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=[{"count": "5"}])]
    )
    assert get_json(URL, {}, {}) == [{"count": "5"}]
    assert route.call_count == 2


@respx.mock
def test_full_carto_queue_is_retried(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.RETRY_SECONDS", 0)
    route = respx.get(URL).mock(
        side_effect=[
            httpx.Response(400, json={"error": ["query_wait_timeout"]}),
            httpx.Response(200, json=[{"count": "7"}]),
        ]
    )
    assert get_json(URL, {}, {}) == [{"count": "7"}]
    assert route.call_count == 2


@respx.mock
def test_bad_query_is_not_retried(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.RETRY_SECONDS", 0)
    route = respx.get(URL).mock(
        return_value=httpx.Response(400, json={"error": ["column does not exist"]})
    )
    with pytest.raises(RuntimeError, match="400"):
        get_json(URL, {}, {})
    assert route.call_count == 1


def test_retry_after_wait_is_capped():
    response = httpx.Response(429, headers={"Retry-After": "86400"})
    assert retry_delay(response, 1) == 60.0
