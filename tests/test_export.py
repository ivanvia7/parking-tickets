import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

from parking_tickets import cache, cities, export
from parking_tickets.schema import to_ticket

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "la.json").read_text())


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    conn = cache.open_cache(tmp_path / "c.db")
    city = cities.load("la")
    cache.save_day(
        conn, "la", "2025-06-03", (to_ticket(city, r) for r in FIXTURE), True
    )
    return conn


@pytest.mark.parametrize("suffix", [".csv", ".jsonl", ".db", ".parquet"])
def test_every_format_keeps_row_count(conn, tmp_path, suffix):
    out = tmp_path / f"t{suffix}"
    export.export(conn, ["la"], "2025-06-03", "2025-06-03", out)
    if suffix == ".db":
        count = (
            sqlite3.connect(out).execute("SELECT count(*) FROM tickets").fetchone()[0]
        )
    else:
        count = duckdb.execute(f"SELECT count(*) FROM '{out}'").fetchall()[0][0]
    assert count == len(FIXTURE)


def test_csv_starts_with_bom(conn, tmp_path):
    out = tmp_path / "t.csv"
    export.export(conn, ["la"], "2025-06-03", "2025-06-03", out)
    assert out.read_bytes().startswith(b"\xef\xbb\xbfcity,source_id")


def test_unknown_suffix_fails(conn, tmp_path):
    with pytest.raises(ValueError):
        export.export(conn, ["la"], "2025-06-03", "2025-06-03", tmp_path / "t.xlsx")


def test_until_day_keeps_last_second_and_date_only_rows(tmp_path):
    conn = cache.open_cache(tmp_path / "c.db")
    base = to_ticket(cities.load("la"), FIXTURE[0])
    stamps = ["2025-06-03T23:59:59", "2025-06-03", "2025-06-04T00:00:00"]
    tickets = [
        replace(base, source_id=str(i), issued_at=s) for i, s in enumerate(stamps)
    ]
    cache.save_day(conn, "la", "2025-06-03", tickets, True)
    out = tmp_path / "t.jsonl"
    export.export(conn, ["la"], "2025-06-03", "2025-06-03", out)
    kept = [json.loads(line)["issued_at"] for line in out.read_text().splitlines()]
    assert sorted(kept) == ["2025-06-03", "2025-06-03T23:59:59"]


def test_parquet_path_with_quote(conn, tmp_path):
    out = tmp_path / "Bob's.parquet"
    export.export(conn, ["la"], "2025-06-03", "2025-06-03", out)
    assert duckdb.execute(f"SELECT count(*) FROM {export.sql_text(out)}").fetchall()[0][
        0
    ] == len(FIXTURE)
