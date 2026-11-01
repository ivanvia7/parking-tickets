from collections.abc import Iterator
from datetime import date, timedelta

from parking_tickets.portals.http import get_json

PAGE_SIZE = 50_000


def sql_url(host: str) -> str:
    return f"https://{host}/api/v2/sql"


def span_filter(date_field: str, since: str, until: str) -> str:
    """Days since..until, both included."""
    after = (date.fromisoformat(until) + timedelta(days=1)).isoformat()
    return f"{date_field} >= '{since}' AND {date_field} < '{after}'"


def query(host: str, sql: str) -> list[dict]:
    return get_json(sql_url(host), {"q": sql}, {})["rows"]


def read(
    host: str, table: str, columns: list[str], where: str, page_size: int = PAGE_SIZE
) -> Iterator[dict]:
    select = ", ".join(columns)
    offset = 0
    while True:
        sql = (
            f"SELECT {select} FROM {table} WHERE {where}"
            f" ORDER BY cartodb_id LIMIT {page_size} OFFSET {offset}"
        )
        page = query(host, sql)
        yield from page
        if len(page) < page_size:
            return
        offset += page_size


def read_day(city: dict, day: str) -> Iterator[dict]:
    columns = [city["date_field"], *city["columns"].values()]
    where = span_filter(city["date_field"], day, day)
    return read(city["host"], city["dataset"], columns, where)


def count_by(city: dict, column: str, since: str, until: str) -> dict[str | None, int]:
    """Tickets per value of one city column, counted by the portal, not fetched."""
    where = span_filter(city["date_field"], since, until)
    sql = (
        f"SELECT {column} AS key, count(*) AS n FROM {city['dataset']}"
        f" WHERE {where} GROUP BY {column}"
    )
    return {row["key"]: int(row["n"]) for row in query(city["host"], sql)}


def sample(city: dict, columns: list[str], limit: int) -> list[dict]:
    """Newest rows, only the given columns; the portal rejects a missing column."""
    sql = (
        f"SELECT {', '.join(columns)} FROM {city['dataset']}"
        f" WHERE {city['date_field']} IS NOT NULL ORDER BY {city['date_field']} DESC LIMIT {limit}"
    )
    return query(city["host"], sql)


def summary(city: dict) -> tuple[int, str | None, str | None]:
    """Rows and first and last ticket date of the table, future typos left out."""
    field = city["date_field"]
    sql = (
        f"SELECT count(*) AS n, min({field}) AS first, max({field}) AS last"
        f" FROM {city['dataset']} WHERE {field} <= now()"
    )
    (row,) = query(city["host"], sql)
    first, last = row.get("first"), row.get("last")
    return int(row["n"]), first and first[:10], last and last[:10]
