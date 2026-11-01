import os
import sqlite3
import warnings
from collections.abc import Iterator
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from parking_tickets import cache, cities, export, fines
from parking_tickets.portals import carto, socrata
from parking_tickets.schema import COLUMNS, Ticket, to_ticket

if TYPE_CHECKING:
    import pandas

PORTALS = {"socrata": socrata.read_day, "carto": carto.read_day}
# Portals upload late: on 2026-11-01 LA had 4,741 tickets for 2026-10-30 against
# about 7,300 on a full weekday. Days newer than this are re-read on every fetch.
# Known limit: late NYC tickets still arrive months later; upgrade is `fetch --refresh`.
SETTLE_DAYS = 30


def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "parking-tickets" / "cache.db"


def days(since: date, until: date) -> Iterator[str]:
    for offset in range((until - since).days + 1):
        yield (since + timedelta(days=offset)).isoformat()


def is_settled(day: str) -> bool:
    return date.fromisoformat(day) <= date.today() - timedelta(days=SETTLE_DAYS)


def parse_rows(
    city: dict, rows: Iterator[dict], table: dict | None, skipped: list[str]
) -> Iterator[Ticket]:
    """One unreadable row is skipped and noted, not allowed to stop the fetch."""
    for row in rows:
        try:
            yield to_ticket(city, row, table)
        except (KeyError, TypeError, ValueError) as error:
            skipped.append(f"{error!r} in {row}")


def fetch_day(
    conn: sqlite3.Connection, city: dict, day: str, skipped: list[str]
) -> int:
    rows = PORTALS[city["portal"]](city, day)
    before = len(skipped)
    tickets = list(parse_rows(city, rows, fines.load_table(city), skipped))
    # A day with skipped rows stays open, so a fixed city file can read it again.
    settled = is_settled(day) and len(skipped) == before
    return cache.save_day(conn, city["slug"], day, tickets, settled)


def fetch(
    conn: sqlite3.Connection, slug: str, since: date, until: date
) -> tuple[int, list[str]]:
    """Fetch every day not already cached; returns rows saved and rows skipped."""
    city = cities.load(slug)
    fetched = 0
    skipped: list[str] = []
    for day in days(since, until):
        if cache.is_fetched(conn, slug, day):
            continue
        try:
            fetched += fetch_day(conn, city, day, skipped)
        except (RuntimeError, ValueError) as error:
            raise RuntimeError(f"{slug} {day}: {error}") from error
    return fetched, skipped


def import_pandas() -> "pandas":
    try:
        import pandas
    except ImportError:
        raise ImportError(
            'load() needs pandas: pip install "parking-tickets[pandas]"'
        ) from None
    return pandas


def load(
    city: str,
    since: str | date,
    until: str | date | None = None,
    cache_path: Path | None = None,
) -> "pandas.DataFrame":
    """One city's tickets as a DataFrame; days not cached yet are fetched first."""
    pd = import_pandas()
    first = date.fromisoformat(str(since))
    last = date.fromisoformat(str(until)) if until else date.today() - timedelta(1)
    if first > last:
        raise ValueError(f"since {first} is after until {last}")
    with closing(cache.open_cache(cache_path or default_cache_path())) as conn:
        _, skipped = fetch(conn, city, first, last)
        rows = list(
            export.select_rows(conn, [city], first.isoformat(), last.isoformat())
        )
    if skipped:
        warnings.warn(f"{city}: {len(skipped)} unreadable rows skipped", stacklevel=2)
    return pd.DataFrame.from_records(rows, columns=list(COLUMNS))
