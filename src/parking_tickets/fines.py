from functools import cache

from parking_tickets.portals.socrata import read


@cache
def fetch_table(host: str, dataset: str, code_field: str) -> dict[str, dict]:
    return {row[code_field]: row for row in read(host, dataset, "1=1")}


def load_table(city: dict) -> dict[str, dict] | None:
    """Fine per violation code, for cities that publish fines in a separate table."""
    lookup = city.get("fine_lookup")
    if lookup is None:
        return None
    return fetch_table(lookup["host"], lookup["dataset"], lookup["code_field"])
