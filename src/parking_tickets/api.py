import os
import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

from parking_tickets import cache, cities, fines
from parking_tickets.portals import carto, socrata
from parking_tickets.schema import to_ticket

PORTALS = {"socrata": socrata.read_day, "carto": carto.read_day}
# Portals upload late: on 2026-11-01 LA had 4,741 tickets for 2026-10-30 against
# about 7,300 on a full weekday. Days newer than this are re-read on every fetch.
# ponytail: late NYC tickets still arrive months later; upgrade is `fetch --refresh`.
SETTLE_DAYS = 30


def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "parking-tickets" / "cache.db"


def days(since: date, until: date) -> Iterator[str]:
    for offset in range((until - since).days + 1):
        yield (since + timedelta(days=offset)).isoformat()


def is_settled(day: str) -> bool:
    return date.fromisoformat(day) <= date.today() - timedelta(days=SETTLE_DAYS)


def fetch_day(conn: sqlite3.Connection, city: dict, day: str) -> int:
    rows = PORTALS[city["portal"]](city, day)
    table = fines.load_table(city)
    tickets = (to_ticket(city, row, table) for row in rows)
    return cache.save_day(conn, city["slug"], day, tickets, is_settled(day))


def fetch(conn: sqlite3.Connection, slug: str, since: date, until: date) -> int:
    """Fetch every day not already cached; returns rows fetched."""
    city = cities.load(slug)
    fetched = 0
    for day in days(since, until):
        if cache.is_fetched(conn, slug, day):
            continue
        try:
            fetched += fetch_day(conn, city, day)
        except Exception as error:
            raise RuntimeError(f"{slug} {day}: {error}") from error
    return fetched
