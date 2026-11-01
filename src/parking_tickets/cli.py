import argparse
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path

from parking_tickets import api, cache


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
    return parser


def run_fetch(args: argparse.Namespace) -> None:
    conn = cache.open_cache(args.cache)
    for slug in args.city.split(","):
        rows = api.fetch(conn, slug.strip(), args.since, args.until)
        print(f"{slug}: {rows} new rows")


def main() -> None:
    args = build_parser().parse_args()
    if args.since > args.until:
        raise SystemExit("--since is after --until")
    run_fetch(args)
