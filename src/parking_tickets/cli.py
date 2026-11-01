import argparse
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path

from parking_tickets import api, cache, export


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parking-tickets")
    parser.add_argument(
        "--version", action="version", version=version("parking-tickets")
    )
    commands = parser.add_subparsers(dest="command", required=True)
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
    return parser


def run_fetch(args: argparse.Namespace) -> None:
    slugs = [s.strip() for s in args.city.split(",")]
    conn = cache.open_cache(args.cache)
    for slug in slugs:
        rows = api.fetch(conn, slug, args.since, args.until)
        print(f"{slug}: {rows} new rows")
    if args.out:
        since, until = args.since.isoformat(), args.until.isoformat()
        export.export(conn, slugs, since, until, args.out)
        print(f"wrote {args.out}")


def main() -> None:
    args = build_parser().parse_args()
    if args.since > args.until:
        raise SystemExit("--since is after --until")
    run_fetch(args)
