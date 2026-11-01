import tomllib
from importlib.resources import files

CITY_DIR = files("parking_tickets") / "cities"


def slugs() -> list[str]:
    return sorted(
        p.name.removesuffix(".toml")
        for p in CITY_DIR.iterdir()
        if p.name.endswith(".toml")
    )


def load(slug: str) -> dict:
    path = CITY_DIR / f"{slug}.toml"
    if not path.is_file():
        raise ValueError(f"unknown city {slug!r}; known: {', '.join(slugs())}")
    return tomllib.loads(path.read_text(encoding="utf-8"))
