from parking_tickets import api, cities, fines
from parking_tickets.portals import carto, socrata

SAMPLE_SIZE = 100
SAMPLERS = {"socrata": socrata.sample, "carto": carto.sample}


def city_columns(city: dict) -> list[str]:
    """Every city column the city file names, each once."""
    names = [
        city["date_field"],
        city.get("time_field"),
        city.get("fine_lookup", {}).get("zone_field"),
    ]
    for source in city["columns"].values():
        names.extend([source] if isinstance(source, str) else source)
    return [name for name in dict.fromkeys(names) if name]


def check_city(slug: str) -> tuple[int, int]:
    """Read the newest live rows through the city file; returns rows, unreadable."""
    city = cities.load(slug)
    where = f"{slug} ({city['host']} {city.get('dataset', 'fiscal-year datasets')})"
    try:
        rows = SAMPLERS[city["portal"]](city, city_columns(city), SAMPLE_SIZE)
        table = fines.load_table(city)
    except (RuntimeError, KeyError) as error:
        raise RuntimeError(f"{where}: {error!r}") from error
    if not rows:
        raise RuntimeError(f"{where}: portal returned no rows")
    skipped: list[str] = []
    tickets = list(api.parse_rows(city, iter(rows), table, skipped))
    if not tickets:
        raise RuntimeError(f"{where}: none of {len(rows)} rows readable: {skipped[0]}")
    return len(rows), len(skipped)
