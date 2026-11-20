import csv
from functools import cache
from importlib.resources import files

GROUPS_FILE = files("parking_tickets") / "groups.csv"
UNGROUPED = "other"


@cache
def table() -> dict[tuple[str, str], str]:
    """(city slug, city code) -> shared group, read once from groups.csv."""
    lines = GROUPS_FILE.read_text(encoding="utf-8").splitlines()
    return {
        (row["city"], row["code"].strip()): row["group"]
        for row in csv.DictReader(lines)
    }


def group_of(slug: str, code: str | None) -> str:
    """Unknown or blank codes land in `other`, never dropped."""
    if not code:
        return UNGROUPED
    return table().get((slug, code.strip()), UNGROUPED)


def ticket_group(city: dict, code: str | None, text: str | None) -> str:
    """A city with `text_groups_first` lets a text listed in groups.csv beat its code."""
    listed = table().get((city["slug"], (text or "").strip()))
    if city.get("text_groups_first") and listed:
        return listed
    return group_of(city["slug"], code)


def group_key(city: dict) -> str:
    """Our column whose value groups.csv lists; Philadelphia has text only."""
    return city.get("group_by", "violation_code")
