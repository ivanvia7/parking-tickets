import os
from collections.abc import Iterator

from parking_tickets.portals.http import get_json

PAGE_SIZE = 50_000


def auth_headers() -> dict[str, str]:
    token = os.environ.get("SOCRATA_APP_TOKEN")
    return {"X-App-Token": token} if token else {}


def resource_url(host: str, dataset: str) -> str:
    return f"https://{host}/resource/{dataset}.json"


def count(host: str, dataset: str, where: str) -> int:
    params = {"$select": "count(*)", "$where": where}
    rows = get_json(resource_url(host, dataset), params, auth_headers())
    return int(rows[0]["count"])


def read(
    host: str, dataset: str, where: str, page_size: int = PAGE_SIZE
) -> Iterator[dict]:
    offset = 0
    while True:
        params = {
            "$where": where,
            "$order": ":id",
            "$limit": str(page_size),
            "$offset": str(offset),
        }
        page = get_json(resource_url(host, dataset), params, auth_headers())
        yield from page
        if len(page) < page_size:
            return
        offset += page_size


def day_filter(date_field: str, day: str) -> str:
    return f"{date_field} >= '{day}T00:00:00' AND {date_field} < '{day}T23:59:59.999'"


def fiscal_year(day: str, start_month: int) -> int:
    year, month = int(day[:4]), int(day[5:7])
    return year + 1 if month >= start_month else year


def dataset_ids(city: dict, day: str) -> list[str]:
    if "dataset" in city:
        return [city["dataset"]]
    # Late tickets land in the next fiscal year's dataset, so read both.
    year = fiscal_year(day, city["fiscal_year_start_month"])
    by_year = city["datasets_by_fiscal_year"]
    return [by_year[str(y)] for y in (year, year + 1) if str(y) in by_year]


def read_day(city: dict, day: str) -> Iterator[dict]:
    where = day_filter(city["date_field"], day)
    for dataset in dataset_ids(city, day):
        yield from read(city["host"], dataset, where)
