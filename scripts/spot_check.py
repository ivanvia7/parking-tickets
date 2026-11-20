"""Seeded sample of tickets, each compared with its row read straight from the portal.

The portal side is read by hand here, not through the city files, so a wrong city
file shows up as a mismatch. New York fines are compared with the city's own
per-ticket record (Open Parking and Camera Violations), not the code table.
Usage: uv run python scripts/spot_check.py [tickets per city] [seed] > docs/spot-check.md
"""

import random
import sys
import tempfile
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from parking_tickets import api, cache, export
from parking_tickets.schema import COLUMNS

ARCGIS = "https://{host}/{path}/query"
DC_LAYER = "dcgis/rest/services/DCGIS_DATA/Violations_Parking_{year}/MapServer/{index}"
SYRACUSE_LAYER = "bdPqSfflsdgFRVVM/arcgis/rest/services/Parking_Violations_2023_Present/FeatureServer/0"
NYC_TICKETS = "nc67-uf89"
NYC_BY_FISCAL_YEAR = {2024: "8zf9-spf8", 2025: "m5vz-tzqv", 2026: "9mwx-gamw"}
# Each city's data runs past these spans; Philadelphia stops in 2017, Oakland is late.
SPANS = {
    "philadelphia": ("2016-01-01", "2017-12-31"),
    "oakland": ("2024-01-01", "2025-06-30"),
}
DEFAULT_SPAN = ("2024-01-01", "2025-12-31")


def get(url: str, params: dict[str, str]) -> Any:
    response = httpx.get(url, params=params, timeout=300)
    response.raise_for_status()
    return response.json()


def socrata(host: str, dataset: str, where: str) -> list[dict]:
    params = {"$where": where, "$select": ":*, *"}
    return get(f"https://{host}/resource/{dataset}.json", params)


def arcgis(host: str, path: str, where: str) -> list[dict]:
    params = {"where": where, "outFields": "*", "f": "json"}
    body = get(ARCGIS.format(host=host, path=path), params)
    return [feature["attributes"] for feature in body.get("features", [])]


def epoch_day(ms: int, zone: str) -> str:
    return datetime.fromtimestamp(ms / 1000, ZoneInfo(zone)).date().isoformat()


def fiscal_dataset(day: date) -> str:
    return NYC_BY_FISCAL_YEAR[day.year + 1 if day.month >= 7 else day.year]


Reader = Callable[[str, date], list[dict]]
# city -> (fetch the row by ticket id, read date, fine, violation, location from it)
CITIES: dict[str, tuple[Reader, Callable[[dict], tuple]]] = {
    "buffalo": (
        lambda i, d: socrata("data.buffalony.gov", "yvvn-sykd", f"summno='{i}'"),
        lambda r: (
            r["summdt"][:10],
            r.get("origfine"),
            r.get("viodesc"),
            r.get("violation_full_address"),
        ),
    ),
    "dc": (
        lambda i, d: arcgis(
            "maps2.dcgis.dc.gov",
            DC_LAYER.format(year=d.year, index=d.month - 1),
            f"TICKET_NUMBER='{i}'",
        ),
        lambda r: (
            epoch_day(r["ISSUE_DATE"], "America/New_York"),
            r["FINE_AMOUNT"],
            r["VIOLATION_CODE"],
            r["LOCATION"],
        ),
    ),
    "everett": (
        lambda i, d: socrata("data.everettwa.gov", "j78y-rzpy", f"ticket='{i}'"),
        lambda r: (r["date"][:10], None, r.get("article"), r.get("block_address")),
    ),
    "la": (
        lambda i, d: socrata("data.lacity.org", "4f5p-udkv", f"ticket_number='{i}'"),
        lambda r: (
            r["issue_date"][:10],
            r.get("fine_amount"),
            r.get("violation_code"),
            r.get("location"),
        ),
    ),
    "nyc": (
        lambda i, d: socrata(
            "data.cityofnewyork.us", fiscal_dataset(d), f"summons_number='{i}'"
        ),
        lambda r: (
            r["issue_date"][:10],
            "per ticket",
            r.get("violation_code"),
            " ".join(r[k] for k in ("house_number", "street_name") if r.get(k)),
        ),
    ),
    "oakland": (
        lambda i, d: socrata("data.oaklandca.gov", "58em-y96b", f"ticket_num='{i}'"),
        lambda r: (
            r["ticket_iss"][:10],
            r.get("fine_amount"),
            r.get("violation"),
            r.get("location"),
        ),
    ),
    "philadelphia": (
        lambda i, d: get(
            "https://phl.carto.com/api/v2/sql",
            {"q": f"SELECT * FROM parking_violations WHERE anon_ticket_number = '{i}'"},
        )["rows"],
        lambda r: (
            r["issue_datetime"][:10],
            r.get("fine"),
            r.get("violation_desc"),
            r.get("location"),
        ),
    ),
    "sf": (
        lambda i, d: socrata("data.sf.gov", "ab4h-6ztd", f"citation_number='{i}'"),
        lambda r: (
            r["citation_issued_datetime"][:10],
            r.get("fine_amount"),
            r.get("violation"),
            r.get("citation_location"),
        ),
    ),
    # Syracuse writes its local clock as if it were UTC.
    "syracuse": (
        lambda i, d: arcgis(
            "services6.arcgis.com", SYRACUSE_LAYER, f"ticket_number='{i}'"
        ),
        lambda r: (
            epoch_day(r["issued_date"], "UTC"),
            r.get("amount"),
            r.get("description"),
            r.get("location"),
        ),
    ),
    "winnipeg": (
        lambda i, d: socrata("data.winnipeg.ca", "bhrt-29rb", f":id='{i}'"),
        lambda r: (
            r["issue_date"][:10],
            r.get("full_fine"),
            r.get("violation"),
            r.get("street"),
        ),
    ),
}
FIELDS = ("date", "fine", "violation", "location")


def number(value: Any) -> float | None:
    return None if value in (None, "") else float(value)


def nyc_fine(source_id: str) -> float | None:
    rows = socrata(
        "data.cityofnewyork.us", NYC_TICKETS, f"summons_number='{source_id}'"
    )
    return number(rows[0]["fine_amount"]) if rows else None


def tool_tickets(slug: str, day: date, conn: Any) -> list[dict]:
    api.fetch(conn, slug, day, day)
    rows = export.select_rows(conn, [slug], day.isoformat(), day.isoformat())
    return [dict(zip(COLUMNS, row, strict=True)) for row in rows]


def busy_day(
    slug: str, rng: random.Random, per_city: int, conn: Any
) -> tuple[date, list[dict]]:
    """A random day in the city's span holding enough tickets; quiet Sundays are redrawn."""
    first, last = (date.fromisoformat(d) for d in SPANS.get(slug, DEFAULT_SPAN))
    while True:
        day = first + timedelta(rng.randrange((last - first).days + 1))
        tickets = tool_tickets(slug, day, conn)
        if len(tickets) >= per_city:
            return day, tickets


def mismatches(slug: str, ticket: dict, day: date) -> list[tuple[str, Any, Any]]:
    read_row, read_fields = CITIES[slug]
    rows = read_row(ticket["source_id"], day)
    if len(rows) != 1:
        return [("city", ticket["source_id"], f"{len(rows)} portal rows")]
    when, fine, violation, location = read_fields(rows[0])
    if slug == "nyc":
        fine = nyc_fine(ticket["source_id"])
    ours = (
        ticket["issued_at"][:10],
        ticket["fine_usd"],
        ticket["violation_code"] or ticket["violation_text"],
        ticket["location"],
    )
    theirs = (when, number(fine), violation, location)
    wrong = []
    for field, mine, source in zip(FIELDS, ours, theirs, strict=True):
        # An empty fine is "not published", never a wrong amount.
        if field == "fine" and mine is None:
            continue
        if mine != source:
            wrong.append((field, mine, source))
    return wrong


def main() -> None:
    per_city = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    seed = sys.argv[2] if len(sys.argv) > 2 else "20261120"
    checked, findings = 0, []
    with (
        tempfile.TemporaryDirectory() as folder,
        closing(cache.open_cache(Path(folder) / "cache.db")) as conn,
    ):
        for slug in sorted(CITIES):
            rng = random.Random(f"{seed}-{slug}")
            day, tickets = busy_day(slug, rng, per_city, conn)
            ordered = sorted(tickets, key=lambda t: t["source_id"])
            for ticket in rng.sample(ordered, per_city):
                checked += 1
                findings += [
                    (slug, day, ticket["source_id"], *w)
                    for w in mismatches(slug, ticket, day)
                ]
    print(
        f"# Spot check\n\nSeed `{seed}`, {per_city} tickets per city, {checked} tickets."
    )
    print(
        f"Run {datetime.now(UTC).date()} with `{' '.join(['scripts/spot_check.py', *sys.argv[1:]])}`.\n"
    )
    print(
        f"Tickets with a wrong field: {len({f[2] for f in findings})} of {checked}.\n"
    )
    if findings:
        print(
            "| City | Day | Ticket | Field | Ours | Portal |\n|---|---|---|---|---|---|"
        )
        for slug, day, source_id, field, mine, source in findings:
            print(f"| {slug} | {day} | {source_id} | {field} | {mine} | {source} |")


if __name__ == "__main__":
    main()
