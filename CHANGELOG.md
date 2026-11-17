# Changelog

## Unreleased

### Added
- City: Buffalo NY (2007 on), grouped by its violation text.

## 0.2.0 - 2026-11-17

### Added
- Cities: Washington DC (2009 on) and Syracuse NY (2023 on), read from ArcGIS servers.

### Fixed
- Syracuse's November to March odd/even rule now groups as `street_cleaning`, not `other`.
- DC's first and last dates in `stats` no longer show a day early.
- A call to a city server now stops after 300 s, and ArcGIS busy answers are tried again.

## 0.1.0 - 2026-11-01

First release.

### Added
- Cities: Los Angeles, New York City (fiscal-year datasets, fines from the city's code table), San Francisco, Philadelphia (2012 to 2017), Oakland, Winnipeg and Everett WA.
- `fetch` into a local SQLite cache, with `--out` to CSV, JSON Lines, SQLite or Parquet.
- New York violation text from the city's code table.
- Points outside a city's limits are treated as geocoding errors and left empty.
- 21 shared violation groups in `groups.csv`.
- `stats`, `cities` and `check-city` commands.
- `load()` returns a pandas DataFrame.
- `CITIES.md` built from the city files with live row counts.
- Monthly `data-YYYY-MM` release: Parquet and gzipped CSV per city and year, with `MANIFEST.json`.
