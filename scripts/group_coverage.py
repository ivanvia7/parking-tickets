"""Share of one city's tickets that groups.csv places outside `other`.

Counts per code come from the portal (a GROUP BY query), so no tickets are
downloaded. Usage: uv run python scripts/group_coverage.py la 2025-06-01 2025-06-30
"""

import sys

from parking_tickets import cities, groups
from parking_tickets.portals import carto, socrata

COUNTERS = {"socrata": socrata.count_by, "carto": carto.count_by}


def coverage(slug: str, since: str, until: str) -> tuple[float, list[tuple]]:
    city = cities.load(slug)
    column = city["columns"][groups.group_key(city)]
    counts = COUNTERS[city["portal"]](city, column, since, until)
    total = sum(counts.values())
    if total == 0:
        raise SystemExit(f"{slug}: no tickets from {since} to {until}")
    missed = [
        (n, code)
        for code, n in counts.items()
        if groups.group_of(slug, code) == groups.UNGROUPED
    ]
    return 1 - sum(n for n, _ in missed) / total, sorted(missed, key=lambda m: -m[0])


def main() -> None:
    slug, since, until = sys.argv[1:4]
    share, missed = coverage(slug, since, until)
    print(f"{slug} {since}..{until}: {share:.1%} outside other")
    for n, code in missed[:10]:
        print(f"  {n:>8}  {code!r}")


if __name__ == "__main__":
    main()
