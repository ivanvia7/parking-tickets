import re
from dataclasses import dataclass, fields

from parking_tickets import groups


@dataclass(frozen=True, slots=True)
class Ticket:
    city: str
    source_id: str
    issued_at: str
    violation_code: str | None
    violation_text: str | None
    group: str
    fine_usd: float | None
    location: str | None
    lat: float | None
    lon: float | None
    plate_state: str | None


COLUMNS = tuple(f.name for f in fields(Ticket))


def number(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def coordinate(value: object) -> float | None:
    # Portals write 0 for "no location"; no ticket is issued at 0,0.
    parsed = number(value)
    return None if parsed == 0 else parsed


def hmm_time(value: str) -> str | None:
    """'904' -> '09:04'; None when the city wrote something unreadable."""
    digits = value.zfill(4)
    if not re.fullmatch(r"([01]\d|2[0-3])[0-5]\d", digits):
        return None
    return f"{digits[:2]}:{digits[2:]}"


def hhmmp_time(value: str) -> str | None:
    """'1008P' -> '22:08'; None when the city wrote something unreadable."""
    match = re.fullmatch(r"(\d\d)(\d\d)([AP])", value)
    if not match or int(match[1]) > 12 or int(match[2]) > 59:
        return None
    hour = int(match[1]) % 12 + (12 if match[3] == "P" else 0)
    return f"{hour:02}:{match[2]}"


TIME_FORMATS = {"hmm": hmm_time, "hhmmp": hhmmp_time}


def issued_at(city: dict, row: dict) -> str:
    raw = row.get(city["date_field"])
    if not raw:
        raise ValueError(f"blank {city['date_field']}")
    stamp = raw[:19]
    time_field = city.get("time_field")
    if not time_field:
        return stamp
    time_raw = row.get(time_field)
    clock = TIME_FORMATS[city["time_format"]](str(time_raw)) if time_raw else None
    # An unreadable time keeps the day only; a made-up time would mislead.
    return f"{stamp[:10]}T{clock}:00" if clock else stamp[:10]


def place(city: dict, lat_raw: object, lon_raw: object) -> tuple[float | None, ...]:
    """Both or neither; a point outside the city's box is a geocoding error."""
    lat, lon = coordinate(lat_raw), coordinate(lon_raw)
    box = city.get("bounds")
    if lat is None or lon is None:
        return None, None
    if box and not (
        box["lat"][0] <= lat <= box["lat"][1] and box["lon"][0] <= lon <= box["lon"][1]
    ):
        return None, None
    return lat, lon


def code_entry(city: dict, fines: dict | None, row: dict) -> dict:
    """The code table's row for this ticket; empty when there is no table or code."""
    if fines is None:
        return {}
    return fines.get(row.get(city["columns"]["violation_code"])) or {}


def fine_from_table(city: dict, entry: dict, row: dict) -> str | None:
    lookup = city["fine_lookup"]
    in_zone = row.get(lookup["zone_field"]) in lookup["zone_values"]
    # Socrata leaves out empty fields, so a code without an amount has no key.
    return entry.get(lookup["zone_amount_field"] if in_zone else lookup["amount_field"])


def column_text(row: dict, source: str | list[str] | None) -> str | None:
    """A list of city columns is joined with spaces, e.g. house number + street."""
    if source is None:
        return None
    if isinstance(source, str):
        return row.get(source)
    parts = [row[name] for name in source if row.get(name)]
    return " ".join(parts) or None


def required_text(row: dict, column: str) -> str:
    value = row.get(column)
    if value in (None, ""):
        raise ValueError(f"blank {column}")
    return str(value)


def to_ticket(city: dict, row: dict, fines: dict | None = None) -> Ticket:
    col = city["columns"]

    def text(name: str) -> str | None:
        return column_text(row, col.get(name))

    entry = code_entry(city, fines, row)
    fine = fine_from_table(city, entry, row) if fines is not None else text("fine_usd")
    text_field = city.get("fine_lookup", {}).get("text_field")
    lat, lon = place(city, text("lat"), text("lon"))

    return Ticket(
        city=city["slug"],
        source_id=required_text(row, col["source_id"]),
        issued_at=issued_at(city, row),
        violation_code=text("violation_code"),
        violation_text=text("violation_text") or entry.get(text_field),
        group=groups.group_of(city["slug"], text(groups.group_key(city))),
        fine_usd=number(fine),
        location=text("location"),
        lat=lat,
        lon=lon,
        plate_state=text("plate_state"),
    )
