import json
import sqlite3
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
        count = duckdb.sql(f"SELECT count(*) FROM '{out}'").fetchall()[0][0]
    assert count == len(FIXTURE)


def test_csv_starts_with_bom(conn, tmp_path):
    out = tmp_path / "t.csv"
    export.export(conn, ["la"], "2025-06-03", "2025-06-03", out)
    assert out.read_bytes().startswith(b"\xef\xbb\xbfcity,source_id")


def test_unknown_suffix_fails(conn, tmp_path):
    with pytest.raises(ValueError):
        export.export(conn, ["la"], "2025-06-03", "2025-06-03", tmp_path / "t.xlsx")
