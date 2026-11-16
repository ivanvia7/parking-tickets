import httpx
import pytest
import respx

from parking_tickets import cities
from parking_tickets.portals import arcgis

DC = cities.load("dc")
SEPTEMBER = "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Violations_Parking_2026/MapServer/8/query"
# 2025-09-15 08:09 in Washington.
STAMP = 1757938140000


def page(rows: list[dict], more: bool) -> httpx.Response:
    features = [{"attributes": row} for row in rows]
    return httpx.Response(
        200, json={"features": features, "exceededTransferLimit": more}
    )


def test_dc_keeps_one_layer_per_month():
    assert arcgis.layer_paths(DC, "2026-08-31", "2026-09-01") == [
        "dcgis/rest/services/DCGIS_DATA/Violations_Parking_2026/MapServer/7",
        "dcgis/rest/services/DCGIS_DATA/Violations_Parking_2026/MapServer/8",
    ]


def test_syracuse_has_one_layer_from_2023():
    city = cities.load("syracuse")
    assert len(arcgis.layer_paths(city, "2023-01-01", "2026-11-05")) == 1
    assert arcgis.layer_paths(city, "2020-01-01", "2022-12-31") == []


@respx.mock
def test_read_day_pages_while_server_says_more(monkeypatch):
    monkeypatch.setattr(arcgis, "PAGE_SIZE", 1)
    route = respx.get(SEPTEMBER).mock(
        side_effect=[
            page([{"TICKET_NUMBER": "1", "ISSUE_DATE": STAMP}], more=True),
            page([{"TICKET_NUMBER": "2", "ISSUE_DATE": None}], more=False),
        ]
    )
    rows = list(arcgis.read_day(DC, "2026-09-15"))
    assert [r["ISSUE_DATE"] for r in rows] == ["2025-09-15T08:09:00", None]
    assert route.calls[1].request.url.params["resultOffset"] == "1"


@respx.mock
def test_missing_service_holds_no_tickets():
    respx.get(SEPTEMBER).mock(
        return_value=httpx.Response(
            200, json={"error": {"code": 404, "message": "Service not found"}}
        )
    )
    assert list(arcgis.read_day(DC, "2026-09-15")) == []


@respx.mock
def test_bad_query_names_the_url():
    respx.get(SEPTEMBER).mock(
        return_value=httpx.Response(
            200, json={"error": {"code": 400, "message": "Invalid field"}}
        )
    )
    with pytest.raises(RuntimeError, match=r"Invalid field.*Violations_Parking_2026"):
        list(arcgis.read_day(DC, "2026-09-15"))


@respx.mock
def test_count_by_reads_upper_cased_names():
    respx.get(SEPTEMBER).mock(
        return_value=page(
            [{"VIOLATION_CODE": "P281", "N": 7}, {"VIOLATION_CODE": None, "N": 1}],
            more=False,
        )
    )
    assert arcgis.count_by(DC, "VIOLATION_CODE", "2026-09-01", "2026-09-30") == {
        "P281": 7,
        None: 1,
    }
