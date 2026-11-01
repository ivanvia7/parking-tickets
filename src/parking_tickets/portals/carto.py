from collections.abc import Iterator
from datetime import date, timedelta

from parking_tickets.portals.http import get_json

PAGE_SIZE = 50_000


def sql_url(host: str) -> str:
    return f"https://{host}/api/v2/sql"


def day_filter(date_field: str, day: str) -> str:
    next_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    return f"{date_field} >= '{day}' AND {date_field} < '{next_day}'"


def query(host: str, sql: str) -> list[dict]:
    return get_json(sql_url(host), {"q": sql}, {})["rows"]


def count(host: str, table: str, where: str) -> int:
    return int(query(host, f"SELECT count(*) FROM {table} WHERE {where}")[0]["count"])


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
    where = day_filter(city["date_field"], day)
    return read(city["host"], city["dataset"], columns, where)
