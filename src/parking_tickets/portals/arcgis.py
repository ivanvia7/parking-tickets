import json
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from parking_tickets.portals.http import get_json

# The lowest maxRecordCount among the city servers; a page never comes back cut.
PAGE_SIZE = 1000


def months(since: str, until: str) -> Iterator[date]:
    month = date.fromisoformat(since).replace(day=1)
    while month <= date.fromisoformat(until):
        yield month
        month = (month + timedelta(days=32)).replace(day=1)


def layer_paths(city: dict, since: str, until: str) -> list[str]:
    """Layers holding days since..until, oldest first.

    `layers` maps the first day a layer covers to its path; DC's path names
    the year and month, as it keeps one table per month.
    """
    starts = sorted(city["layers"])
    paths: list[str] = []
    for month in months(max(since, starts[0]), until):
        start = max(s for s in starts if s <= month.isoformat())
        path = city["layers"][start].format(
            year=month.year, month_index=month.month - 1
        )
        if path not in paths:
            paths.append(path)
    return paths


def all_paths(city: dict) -> list[str]:
    return layer_paths(city, min(city["layers"]), date.today().isoformat())


def span_filter(date_field: str, since: str, until: str) -> str:
    """Days since..until, both included, in the server's own time zone."""
    after = (date.fromisoformat(until) + timedelta(days=1)).isoformat()
    return (
        f"{date_field} >= TIMESTAMP '{since} 00:00:00'"
        f" AND {date_field} < TIMESTAMP '{after} 00:00:00'"
    )


def local_text(city: dict, epoch_ms: int) -> str:
    """Epoch milliseconds as the city's wall clock, the text Socrata would send."""
    moment = datetime.fromtimestamp(epoch_ms / 1000, ZoneInfo(city["time_zone"]))
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def field(attributes: dict, name: str) -> Any:
    """DC answers statistics with upper-cased names; match without case."""
    lowered = {key.lower(): value for key, value in attributes.items()}
    return lowered.get(name.lower())


def query(city: dict, path: str, params: dict[str, str]) -> dict:
    url = f"https://{city['host']}/{path}/query"
    body = get_json(url, {**params, "f": "json"}, {})
    # ArcGIS answers a bad query with HTTP 200 and an error object.
    # DC opens next year's service in January; until then the year holds no tickets.
    if body.get("error", {}).get("code") == 404:
        return {"features": []}
    if "error" in body:
        raise RuntimeError(f"{body['error']} from {url}")
    return body


def rows_of(city: dict, body: dict) -> list[dict]:
    rows = [feature["attributes"] for feature in body["features"]]
    for row in rows:
        stamp = row.get(city["date_field"])
        row[city["date_field"]] = None if stamp is None else local_text(city, stamp)
    return rows


def read_day(city: dict, day: str) -> Iterator[dict]:
    where = span_filter(city["date_field"], day, day)
    for path in layer_paths(city, day, day):
        offset = 0
        while True:
            body = query(
                city,
                path,
                {
                    "where": where,
                    "outFields": "*",
                    "orderByFields": city["columns"]["source_id"],
                    "resultOffset": str(offset),
                    "resultRecordCount": str(PAGE_SIZE),
                },
            )
            yield from rows_of(city, body)
            if not body.get("exceededTransferLimit"):
                break
            offset += PAGE_SIZE


def statistics(*stats: tuple[str, str, str]) -> str:
    return json.dumps(
        [
            {
                "statisticType": kind,
                "onStatisticField": on,
                "outStatisticFieldName": name,
            }
            for kind, on, name in stats
        ]
    )


def count_by(city: dict, column: str, since: str, until: str) -> dict[str | None, int]:
    """Tickets per value of one city column, counted by the portal, not fetched."""
    params = {
        "where": span_filter(city["date_field"], since, until),
        "groupByFieldsForStatistics": column,
        "outStatistics": statistics(("count", city["columns"]["source_id"], "n")),
    }
    counts: dict[str | None, int] = {}
    for path in layer_paths(city, since, until):
        for feature in query(city, path, params)["features"]:
            key = field(feature["attributes"], column)
            key = None if key is None else str(key)
            counts[key] = counts.get(key, 0) + int(field(feature["attributes"], "n"))
    return counts


def sample(city: dict, columns: list[str], limit: int) -> list[dict]:
    """Newest rows of the newest layer that has any; DC opens a month's table early."""
    params = {
        "where": f"{city['date_field']} IS NOT NULL",
        "outFields": ",".join(columns),
        "orderByFields": f"{city['date_field']} DESC",
        "resultRecordCount": str(limit),
    }
    for path in reversed(all_paths(city)):
        rows = rows_of(city, query(city, path, params))
        if rows:
            return rows
    return []


def summary(city: dict) -> tuple[int, str | None, str | None]:
    """Rows and first and last ticket date over all the city's layers.

    Tickets dated after today are typos and are left out of the dates.
    """
    date_field = city["date_field"]
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    params = {
        "where": f"{date_field} < TIMESTAMP '{tomorrow} 00:00:00'",
        "outStatistics": statistics(
            ("count", city["columns"]["source_id"], "n"),
            ("min", date_field, "first"),
            ("max", date_field, "last"),
        ),
    }
    total, firsts, lasts = 0, [], []
    for path in all_paths(city):
        for feature in query(city, path, params)["features"]:
            row = feature["attributes"]
            total += int(field(row, "n") or 0)
            first, last = field(row, "first"), field(row, "last")
            firsts += [local_text(city, first)[:10]] if first is not None else []
            lasts += [local_text(city, last)[:10]] if last is not None else []
    return total, min(firsts, default=None), max(lasts, default=None)
