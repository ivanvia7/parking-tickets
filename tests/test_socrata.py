import httpx
import respx

from parking_tickets.portals import socrata

URL = "https://data.lacity.org/resource/4f5p-udkv.json"


@respx.mock
def test_read_pages_until_short_page(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.MIN_GAP_SECONDS", 0)
    route = respx.get(URL).mock(
        side_effect=[
            httpx.Response(200, json=[{"n": 1}, {"n": 2}]),
            httpx.Response(200, json=[{"n": 3}]),
        ]
    )
    rows = list(socrata.read("data.lacity.org", "4f5p-udkv", "1=1", page_size=2))
    assert [r["n"] for r in rows] == [1, 2, 3]
    assert route.calls[1].request.url.params["$offset"] == "2"


@respx.mock
def test_count_reads_number():
    respx.get(URL).mock(return_value=httpx.Response(200, json=[{"count": "7886"}]))
    assert socrata.count("data.lacity.org", "4f5p-udkv", "1=1") == 7886
