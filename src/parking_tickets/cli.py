import argparse
from datetime import date, timedelta
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path

from parking_tickets import api, cache, check, cities, export


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parking-tickets")
    parser.add_argument(
        "--version", action="version", version=version("parking-tickets")
    )
    commands = parser.add_subparsers(dest="command", required=True)
    add_fetch(commands)
    add_stats(commands)
    add_check_city(commands)
    commands.add_parser("cities", help="list city slugs").set_defaults(
        run=lambda parser, args: print("\n".join(cities.slugs()))
    )
    return parser


def add_fetch(commands: argparse._SubParsersAction) -> None:
    fetch = commands.add_parser("fetch", help="fetch tickets into the local cache")
    fetch.add_argument("--city", required=True, help="comma list, e.g. la,sf")
    fetch.add_argument("--since", required=True, type=date.fromisoformat)
    fetch.add_argument(
        "--until",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=1),
        help="last day to fetch, default yesterday",
    )
    fetch.add_argument("--cache", type=Path, default=api.default_cache_path())
    fetch.add_argument(
        "--out", type=Path, help="write the rows to .csv, .jsonl, .db or .parquet"
    )
    fetch.set_defaults(run=fetch_command)


def add_stats(commands: argparse._SubParsersAction) -> None:
    stats = commands.add_parser("stats", help="rows and coverage per cached city")
    stats.add_argument("--cache", type=Path, default=api.default_cache_path())
    stats.set_defaults(run=stats_command)


def run_fetch(args: argparse.Namespace) -> None:
    slugs = [s.strip() for s in args.city.split(",")]
    conn = cache.open_cache(args.cache)
    for slug in slugs:
        rows, skipped = api.fetch(conn, slug, args.since, args.until)
        print(f"{slug}: {rows} rows read, {len(skipped)} unreadable rows skipped")
        if skipped:
            print(f"  first skipped: {skipped[0][:300]}")
    if args.out:
        since, until = args.since.isoformat(), args.until.isoformat()
        export.export(conn, slugs, since, until, args.out)
        print(f"wrote {args.out}")


def check_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Fail before any download, not after a long fetch."""
    if args.since > args.until:
        parser.error("--since is after --until")
    known = cities.slugs()
    unknown = {s.strip() for s in args.city.split(",")} - set(known)
    if unknown:
        parser.error(
            f"unknown city {', '.join(sorted(unknown))}; known: {', '.join(known)}"
        )
    if not args.out:
        return
    if not args.out.parent.is_dir():
        parser.error(f"--out folder {args.out.parent} does not exist")
    if args.out.suffix not in export.WRITERS:
        parser.error(f"--out must end with one of {', '.join(export.WRITERS)}")
    if args.out.resolve() == args.cache.resolve():
        parser.error("--out must not be the cache file; exporting there would erase it")
    if args.out.suffix == ".parquet" and find_spec("duckdb") is None:
        parser.error('.parquet needs duckdb: pip install "parking-tickets[parquet]"')


def add_check_city(commands: argparse._SubParsersAction) -> None:
    command = commands.add_parser(
        "check-city", help="read 100 live rows through a city file"
    )
    command.add_argument("slug")
    command.set_defaults(run=check_city_command)


def check_city_command(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    if args.slug not in cities.slugs():
        parser.error(f"unknown city {args.slug}; known: {', '.join(cities.slugs())}")
    try:
        rows, skipped = check.check_city(args.slug)
    except RuntimeError as error:
        raise SystemExit(f"FAIL {error}") from None
    print(f"ok {args.slug}: {rows} live rows read, {skipped} unreadable")


def fetch_command(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    check_args(parser, args)
    run_fetch(args)


def stats_command(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cache.is_file():
        parser.error(f"no cache at {args.cache}; run fetch first")
    rows = cache.city_stats(cache.open_cache(args.cache))
    if not rows:
        print(f"{args.cache} holds no tickets")
    for row in rows:
        print(
            f"{row['city']}: {row['rows']} rows, {row['first_day']} to"
            f" {row['last_day']}, {row['with_lat_lon']:.1%} with lat/lon,"
            f" {row['in_other']:.1%} in other"
        )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.run(parser, args)
    except RuntimeError as error:
        # Portal trouble is not a bug in this tool; one line says what failed where.
        raise SystemExit(f"error: {error}") from None
