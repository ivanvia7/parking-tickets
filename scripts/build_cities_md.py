"""Write CITIES.md from the city files, with live row counts from each portal.

Every number comes from one count/min/max query per dataset; no tickets are
downloaded. Usage: uv run python scripts/build_cities_md.py
"""

from datetime import date
from pathlib import Path

from parking_tickets import cities
from parking_tickets.portals import PORTALS

OUT = Path(__file__).resolve().parent.parent / "CITIES.md"
HEADER = """# Cities

Built by `scripts/build_cities_md.py` from the files in `src/parking_tickets/cities/`.
Rows and dates are counted live on each portal. Tickets dated in the future are left out;
a few typo dates in the past (such as 1950) remain, so a first date can look too early.

| City | Slug | Rows | First ticket | Last ticket | Source | Last check |
|---|---|---|---|---|---|---|
"""


def city_line(slug: str, today: str) -> str:
    city = cities.load(slug)
    try:
        rows, first, last = PORTALS[city["portal"]].summary(city)
    except RuntimeError as error:
        raise RuntimeError(f"{slug} ({city['host']}): {error}") from error
    return (
        f"| {city['name']} | `{slug}` | {rows:,} | {first or '?'} | {last or '?'}"
        f" | [{city['host']}]({city['source_url']}) | {today} |"
    )


def main() -> None:
    today = date.today().isoformat()
    lines = [city_line(slug, today) for slug in cities.slugs()]
    OUT.write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(lines)} cities")


if __name__ == "__main__":
    main()
