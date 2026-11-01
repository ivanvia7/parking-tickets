import sqlite3
from collections.abc import Iterable
from dataclasses import astuple
from pathlib import Path

from parking_tickets.schema import COLUMNS, Ticket

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS tickets (
    {", ".join(f'"{c}"' for c in COLUMNS)},
    PRIMARY KEY (city, source_id)
);
CREATE TABLE IF NOT EXISTS fetched_days (
    city TEXT NOT NULL,
    day TEXT NOT NULL,
    rows INTEGER NOT NULL,
    PRIMARY KEY (city, day)
);
"""


def open_cache(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_day(
    conn: sqlite3.Connection,
    city: str,
    day: str,
    tickets: Iterable[Ticket],
    settled: bool,
) -> int:
    """Store a day's tickets; only a settled day is skipped by later fetches."""
    rows = [astuple(t) for t in tickets]
    marks = ", ".join("?" for _ in COLUMNS)
    with conn:
        conn.execute(
            "DELETE FROM tickets WHERE city = ? AND substr(issued_at, 1, 10) = ?",
            (city, day),
        )
        conn.executemany(f"INSERT OR REPLACE INTO tickets VALUES ({marks})", rows)
        if settled:
            conn.execute(
                "INSERT OR REPLACE INTO fetched_days VALUES (?, ?, ?)",
                (city, day, len(rows)),
            )
    return len(rows)


def is_fetched(conn: sqlite3.Connection, city: str, day: str) -> bool:
    query = "SELECT 1 FROM fetched_days WHERE city = ? AND day = ?"
    return conn.execute(query, (city, day)).fetchone() is not None


STATS_QUERY = """
SELECT city, count(*), min(substr(issued_at, 1, 10)), max(substr(issued_at, 1, 10)),
       avg(lat IS NOT NULL AND lon IS NOT NULL), avg("group" = 'other')
FROM tickets GROUP BY city ORDER BY city
"""
STATS_COLUMNS = ("city", "rows", "first_day", "last_day", "with_lat_lon", "in_other")


def city_stats(conn: sqlite3.Connection) -> list[dict]:
    """Rows, date range and the share with lat/lon and in `other`, per city."""
    return [
        dict(zip(STATS_COLUMNS, row, strict=True)) for row in conn.execute(STATS_QUERY)
    ]
