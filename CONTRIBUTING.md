# Contributing

## A dataset link counts

Found a city that publishes parking tickets? Open an issue with the link. That is a full contribution and gets credited in the CHANGELOG. You do not need to write any code.

## Add a city in 3 steps

1. **Write the city file.** Copy `src/parking_tickets/cities/sf.toml` to `src/parking_tickets/cities/<slug>.toml`. Fill in the portal (`socrata` or `carto`), host, dataset id, the date column, and under `[columns]` which city column feeds each of our columns. Leave out a column the city does not publish.
2. **Check it.** Run `uv run parking-tickets check-city <slug>`. It reads 100 live rows through your file and fails on any missing column.
3. **Map the codes.** Run `uv run python scripts/group_coverage.py <slug> 2025-06-01 2025-06-30`. It lists the codes still in `other`, biggest first. Add rows to `src/parking_tickets/groups.csv` until at least 95% of the month is outside `other`. Use only the existing groups listed in the README.

Then run `uv run python scripts/build_cities_md.py` and open a pull request. The `city-check` workflow runs step 2 again on every changed city file.

## Rules

- Never store plate numbers.
- City differences go in the city file or `groups.csv`, not in Python code.
- Tests run offline: `uv run pytest`. Lint: `uv run ruff check` and `uv run ruff format`. Types: `uv run pyright`.
- A new code path gets a test, including its odd input: a blank field, an unknown code, a missing file.
