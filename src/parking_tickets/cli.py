import argparse
from importlib.metadata import version


def main() -> None:
    parser = argparse.ArgumentParser(prog="parking-tickets")
    parser.add_argument(
        "--version", action="version", version=version("parking-tickets")
    )
    parser.parse_args()
