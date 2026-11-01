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
    conn: sqlite3.Connection, city: str, day: str, tickets: Iterable[Ticket]
) -> int:
    rows = [astuple(t) for t in tickets]
    marks = ", ".join("?" for _ in COLUMNS)
    with conn:
        conn.executemany(f"INSERT OR REPLACE INTO tickets VALUES ({marks})", rows)
        conn.execute(
            "INSERT OR REPLACE INTO fetched_days VALUES (?, ?, ?)",
            (city, day, len(rows)),
        )
    return len(rows)


def is_fetched(conn: sqlite3.Connection, city: str, day: str) -> bool:
    query = "SELECT 1 FROM fetched_days WHERE city = ? AND day = ?"
    return conn.execute(query, (city, day)).fetchone() is not None


def last_day(conn: sqlite3.Connection, city: str) -> str | None:
    query = "SELECT max(day) FROM fetched_days WHERE city = ?"
    return conn.execute(query, (city,)).fetchone()[0]
