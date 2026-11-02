"""Build the monthly data release: Parquet and gzipped CSV per city and year.

plan                          JSON matrix of {city, since, until}, one per city-year
build CITY SINCE UNTIL OUT    fetch the days into a fresh cache, write one file pair per year
manifest OUT                  write OUT/MANIFEST.json; fail on a file GitHub would refuse
"""

import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import duckdb

from parking_tickets import api, cache, cities, export
from parking_tickets.export import sql_text

# GitHub refuses release files of 2 GiB or more.
MAX_FILE_BYTES = 2 * 1024**3


def year_spans(first: date, last: date) -> list[tuple[str, str]]:
    return [
        (max(first, date(y, 1, 1)).isoformat(), min(last, date(y, 12, 31)).isoformat())
        for y in range(first.year, last.year + 1)
    ]


def plan() -> list[dict]:
    yesterday = date.today() - timedelta(days=1)
    jobs = []
    for slug in cities.slugs():
        city = cities.load(slug)
        first = date.fromisoformat(city["first_day"])
        last = min(date.fromisoformat(city.get("last_day", "9999-12-31")), yesterday)
        jobs += [
            {"city": slug, "since": since, "until": until}
            for since, until in year_spans(first, last)
        ]
    return jobs


def write_csv_gz(
    conn: sqlite3.Connection, slug: str, since: str, until: str, path: Path
) -> None:
    plain = path.with_suffix("")
    export.export(conn, [slug], since, until, plain)
    with plain.open("rb") as source, gzip.open(path, "wb") as target:
        shutil.copyfileobj(source, target)
    plain.unlink()


def build(slug: str, since: str, until: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        conn = cache.open_cache(Path(tmp) / "cache.db")
        first, last = date.fromisoformat(since), date.fromisoformat(until)
        rows, skipped = api.fetch(conn, slug, first, last)
        print(
            f"{slug} {since}..{until}: {rows} rows, {len(skipped)} unreadable skipped"
        )
        for span_since, span_until in year_spans(first, last):
            stem = out / f"{slug}-{span_since[:4]}"
            export.export(
                conn, [slug], span_since, span_until, stem.with_suffix(".parquet")
            )
            write_csv_gz(
                conn, slug, span_since, span_until, stem.with_suffix(".csv.gz")
            )
        conn.close()


def count_rows(path: Path) -> int:
    reader = "read_parquet" if path.suffix == ".parquet" else "read_csv"
    return duckdb.execute(
        f"SELECT count(*) FROM {reader}({sql_text(path)})"
    ).fetchall()[0][0]


def file_entry(path: Path) -> dict:
    size = path.stat().st_size
    if size >= MAX_FILE_BYTES:
        raise SystemExit(
            f"{path.name} is {size} bytes; GitHub releases take under 2 GiB"
        )
    with path.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    return {
        "file": path.name,
        "rows": count_rows(path),
        "bytes": size,
        "sha256": digest,
    }


def manifest(out: Path) -> Path:
    files = sorted(p for p in out.iterdir() if p.name.endswith((".parquet", ".csv.gz")))
    if not files:
        raise SystemExit(f"no .parquet or .csv.gz files in {out}")
    entries = [file_entry(p) for p in files]
    path = out / "MANIFEST.json"
    body = {"built": date.today().isoformat(), "files": entries}
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    command, *args = sys.argv[1:] or ["help"]
    if command == "plan":
        print(json.dumps(plan()))
    elif command == "build" and len(args) == 4:
        build(args[0], args[1], args[2], Path(args[3]))
    elif command == "manifest" and len(args) == 1:
        print(f"wrote {manifest(Path(args[0]))}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
