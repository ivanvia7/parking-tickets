import csv
import json
import sqlite3
import tempfile
from collections.abc import Iterator
from pathlib import Path

from parking_tickets.cache import SCHEMA
from parking_tickets.schema import COLUMNS

PARQUET_TYPES = {"fine_usd": "DOUBLE", "lat": "DOUBLE", "lon": "DOUBLE"}


def select_rows(
    conn: sqlite3.Connection, slugs: list[str], since: str, until: str
) -> Iterator[tuple]:
    marks = ", ".join("?" for _ in slugs)
    query = (
        f"SELECT * FROM tickets WHERE city IN ({marks})"
        " AND issued_at >= ? AND issued_at < ? ORDER BY city, issued_at"
    )
    # issued_at is ISO text, so "until" plus "T~" sorts after every time that day.
    return conn.execute(query, (*slugs, since, until + "T~"))


def to_csv(rows: Iterator[tuple], path: Path) -> None:
    # utf-8-sig adds the byte-order mark Excel needs to read UTF-8.
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def to_jsonl(rows: Iterator[tuple], path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(
                json.dumps(dict(zip(COLUMNS, row, strict=True)), ensure_ascii=False)
                + "\n"
            )


def to_sqlite(rows: Iterator[tuple], path: Path) -> None:
    path.unlink(missing_ok=True)
    out = sqlite3.connect(path)
    marks = ", ".join("?" for _ in COLUMNS)
    with out:
        out.executescript(SCHEMA)
        out.executemany(f"INSERT INTO tickets VALUES ({marks})", rows)
    out.close()


def to_parquet(rows: Iterator[tuple], path: Path) -> None:
    import duckdb  # only needed here; plain installs skip it

    columns = {c: PARQUET_TYPES.get(c, "VARCHAR") for c in COLUMNS}
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "rows.jsonl"
        to_jsonl(rows, staged)
        duckdb.sql(
            f"COPY (SELECT * FROM read_json({sql_text(staged)}, columns={columns}))"
            f" TO {sql_text(path)} (FORMAT parquet, COMPRESSION zstd)"
        )


def sql_text(path: Path) -> str:
    """Quote a path for duckdb SQL, which takes no parameters in COPY."""
    return "'" + str(path).replace("'", "''") + "'"


WRITERS = {".csv": to_csv, ".jsonl": to_jsonl, ".db": to_sqlite, ".parquet": to_parquet}


def export(
    conn: sqlite3.Connection, slugs: list[str], since: str, until: str, path: Path
) -> None:
    writer = WRITERS.get(path.suffix)
    if writer is None:
        raise ValueError(f"--out must end with one of {', '.join(WRITERS)}")
    writer(select_rows(conn, slugs, since, until), path)
