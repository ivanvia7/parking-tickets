# Changelog

## 0.1.0 - 2026-11-01

First release.

### Added
- Cities: Los Angeles, New York City (fiscal-year datasets, fines from the city's code table), San Francisco, Philadelphia (2012 to 2017).
- `fetch` into a local SQLite cache, with `--out` to CSV, JSON Lines, SQLite or Parquet.
- 21 shared violation groups in `groups.csv`.
- `stats`, `cities` and `check-city` commands.
- `load()` returns a pandas DataFrame.
- `CITIES.md` built from the city files with live row counts.
- Monthly `data-YYYY-MM` release: Parquet and gzipped CSV per city and year, with `MANIFEST.json`.
