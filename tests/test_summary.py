import httpx
import respx

from parking_tickets import cities
from parking_tickets.portals import carto, socrata


@respx.mock
def test_socrata_summary_spans_every_dataset_and_skips_empty_ones():
    city = {
        "host": "h.example",
        "date_field": "d",
        "datasets_by_fiscal_year": {"2024": "aaaa-1111", "2025": "bbbb-2222"},
    }
    respx.get("https://h.example/resource/aaaa-1111.json").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "n": "3",
                    "first": "2023-07-01T00:00:00.000",
                    "last": "2024-06-30T00:00:00.000",
                }
            ],
        )
    )
    respx.get("https://h.example/resource/bbbb-2222.json").mock(
        return_value=httpx.Response(200, json=[{"n": "0"}])
    )
    assert socrata.summary(city) == (3, "2023-07-01", "2024-06-30")


def test_all_datasets_of_a_single_dataset_city():
    assert socrata.all_datasets(cities.load("la")) == ["4f5p-udkv"]


@respx.mock
def test_carto_summary_of_an_empty_table():
    respx.get("https://phl.carto.com/api/v2/sql").mock(
        return_value=httpx.Response(
            200, json={"rows": [{"n": 0, "first": None, "last": None}]}
        )
    )
    assert carto.summary(cities.load("philadelphia")) == (0, None, None)
