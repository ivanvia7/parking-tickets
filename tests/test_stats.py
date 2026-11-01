import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from parking_tickets import cache, cities
from parking_tickets.schema import to_ticket

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "la.json").read_text())


def test_stats_counts_missing_location_and_unknown_codes(tmp_path):
    conn = cache.open_cache(tmp_path / "c.db")
    base = to_ticket(cities.load("la"), FIXTURE[0])
    tickets = [
        base,
        replace(base, source_id="2", lat=None, group="other"),
        replace(base, source_id="3", lon=None, issued_at="2025-06-04"),
        replace(base, source_id="4", group="other"),
    ]
    cache.save_day(conn, "la", "2025-06-03", tickets, True)
    (row,) = cache.city_stats(conn)
    assert row["rows"] == 4
    assert (row["first_day"], row["last_day"]) == ("2025-06-03", "2025-06-04")
    assert row["with_lat_lon"] == pytest.approx(0.5)
    assert row["in_other"] == pytest.approx(0.5)


def test_empty_cache_has_no_stats(tmp_path):
    assert cache.city_stats(cache.open_cache(tmp_path / "c.db")) == []


def run_stats(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["parking-tickets", "stats", "--cache", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_stats_on_missing_cache_fails_without_creating_it(tmp_path):
    path = tmp_path / "none.db"
    result = run_stats(path)
    assert result.returncode == 2 and "run fetch first" in result.stderr
    assert not path.exists()


def test_stats_on_empty_cache_says_so(tmp_path):
    path = tmp_path / "c.db"
    cache.open_cache(path).close()
    result = run_stats(path)
    assert result.returncode == 0 and "holds no tickets" in result.stdout
