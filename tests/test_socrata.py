import httpx
import pytest
import respx

from parking_tickets.portals import socrata

URL = "https://data.lacity.org/resource/4f5p-udkv.json"


@respx.mock
def test_read_pages_until_short_page():
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
def test_html_instead_of_json_names_the_url():
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>down</html>"))
    with pytest.raises(RuntimeError, match=r"not JSON from https://data.lacity.org"):
        list(socrata.read("data.lacity.org", "4f5p-udkv", "1=1"))


@respx.mock
def test_timeout_after_every_try_names_the_url(monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.RETRY_SECONDS", 0)
    route = respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(
        RuntimeError, match=r"ReadTimeout.*data.lacity.org.*after 3 tries"
    ):
        list(socrata.read("data.lacity.org", "4f5p-udkv", "1=1"))
    assert route.call_count == 3
