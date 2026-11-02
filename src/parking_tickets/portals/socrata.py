import os
from collections.abc import Iterator
from datetime import date, timedelta

from parking_tickets.portals.http import get_json

PAGE_SIZE = 50_000


def auth_headers() -> dict[str, str]:
    token = os.environ.get("SOCRATA_APP_TOKEN")
    return {"X-App-Token": token} if token else {}


def resource_url(host: str, dataset: str) -> str:
    return f"https://{host}/resource/{dataset}.json"


def read(host: str, dataset: str, where: str, select: str = "*") -> Iterator[dict]:
    offset = 0

    while True:
        params = {
            "$select": select,
            "$where": where,
            "$order": ":id",
            "$limit": str(PAGE_SIZE),
            "$offset": str(offset),
        }
        page = get_json(resource_url(host, dataset), params, auth_headers())
        yield from page

        if len(page) < PAGE_SIZE:
            return
        offset += PAGE_SIZE


def span_filter(date_field: str, since: str, until: str) -> str:
    """Days since..until, both included."""
    after = (date.fromisoformat(until) + timedelta(days=1)).isoformat()
    return f"{date_field} >= '{since}T00:00:00' AND {date_field} < '{after}T00:00:00'"


def fiscal_year(day: str, start_month: int) -> int:
    year, month = int(day[:4]), int(day[5:7])
    return year + 1 if month >= start_month else year


def dataset_ids(city: dict, day: str) -> list[str]:
    if "dataset" in city:
        return [city["dataset"]]
    # Late tickets land in the next fiscal year's dataset, so read both.
    year = fiscal_year(day, city["fiscal_year_start_month"])
    by_year = city["datasets_by_fiscal_year"]
    if str(year) not in by_year:
        raise ValueError(f"no dataset listed for fiscal year {year}")
    return [by_year[str(y)] for y in (year, year + 1) if str(y) in by_year]


def read_day(city: dict, day: str) -> Iterator[dict]:
    where = span_filter(city["date_field"], day, day)
    # Winnipeg has no ticket number; the portal's row id stands in and is asked for by name.
    source_id = city["columns"]["source_id"]
    select = f"*, {source_id}" if source_id.startswith(":") else "*"
    for dataset in dataset_ids(city, day):
        yield from read(city["host"], dataset, where, select)


def count_by(city: dict, column: str, since: str, until: str) -> dict[str | None, int]:
    """Tickets per value of one city column, counted by the portal, not fetched."""
    params = {
        "$select": f"{column}, count(*) AS n",
        "$where": span_filter(city["date_field"], since, until),
        "$group": column,
        "$limit": str(PAGE_SIZE),
    }
    counts: dict[str | None, int] = {}
    for dataset in dataset_ids(city, since):
        url = resource_url(city["host"], dataset)
        for row in get_json(url, params, auth_headers()):
            key = row.get(column)
            counts[key] = counts.get(key, 0) + int(row["n"])
    return counts


def sample(city: dict, columns: list[str], limit: int) -> list[dict]:
    """Newest rows, only the given columns; the portal rejects a missing column."""
    dataset = dataset_ids(city, date.today().isoformat())[0]
    params = {
        "$select": ", ".join(columns),
        "$where": f"{city['date_field']} IS NOT NULL",
        "$order": f"{city['date_field']} DESC",
        "$limit": str(limit),
    }
    return get_json(resource_url(city["host"], dataset), params, auth_headers())


def all_datasets(city: dict) -> list[str]:
    if "dataset" in city:
        return [city["dataset"]]
    return list(city["datasets_by_fiscal_year"].values())


def summary(city: dict) -> tuple[int, str | None, str | None]:
    """Rows and first and last ticket date over all the city's datasets.

    Tickets dated after today are typos and are left out of the dates.
    """
    field = city["date_field"]
    params = {
        "$select": f"count(*) AS n, min({field}) AS first, max({field}) AS last",
        "$where": f"{field} < '{date.today() + timedelta(days=1)}T00:00:00'",
    }
    total, firsts, lasts = 0, [], []
    for dataset in all_datasets(city):
        url = resource_url(city["host"], dataset)
        (row,) = get_json(url, params, auth_headers())
        total += int(row["n"])
        firsts += [row["first"][:10]] if row.get("first") else []
        lasts += [row["last"][:10]] if row.get("last") else []
    return total, min(firsts, default=None), max(lasts, default=None)
