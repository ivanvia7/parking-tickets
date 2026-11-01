from dataclasses import dataclass, fields


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
UNGROUPED = "other"


def number(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def coordinate(value: object) -> float | None:
    # Portals write 0 for "no location"; no ticket is issued at 0,0.
    parsed = number(value)
    return None if parsed == 0 else parsed


def hmm_time(value: str) -> str:
    """'904' -> '09:04'"""
    digits = value.zfill(4)
    return f"{digits[:2]}:{digits[2:]}"


TIME_FORMATS = {"hmm": hmm_time}


def issued_at(city: dict, row: dict) -> str:
    stamp = row[city["date_field"]][:19]
    time_field = city.get("time_field")
    if not time_field:
        return stamp
    clock = TIME_FORMATS[city["time_format"]](row.get(time_field) or "0")
    return f"{stamp[:10]}T{clock}:00"


def to_ticket(city: dict, row: dict) -> Ticket:
    col = city["columns"]

    def text(name: str) -> str | None:
        return row.get(col[name]) if name in col else None

    return Ticket(
        city=city["slug"],
        source_id=row[col["source_id"]],
        issued_at=issued_at(city, row),
        violation_code=text("violation_code"),
        violation_text=text("violation_text"),
        group=UNGROUPED,
        fine_usd=number(text("fine_usd")),
        location=text("location"),
        lat=coordinate(text("lat")),
        lon=coordinate(text("lon")),
        plate_state=text("plate_state"),
    )
