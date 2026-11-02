"""Write web/cities.json from the city files and groups.csv, so the page never
hand-copies a column name or code. Usage: uv run python scripts/build_web.py
"""

import json
from pathlib import Path

from parking_tickets import cities, groups

OUT = Path(__file__).resolve().parent.parent / "web" / "cities.json"


def web_city(slug: str) -> dict:
    city = cities.load(slug)
    city["groups"] = {
        code: group for (owner, code), group in groups.table().items() if owner == slug
    }
    city["group_column"] = city["columns"].get(groups.group_key(city))
    return city


def main() -> None:
    data = {slug: web_city(slug) for slug in cities.slugs()}
    OUT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(data)} cities")


if __name__ == "__main__":
    main()
