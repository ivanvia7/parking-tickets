# Cities

Built by `scripts/build_cities_md.py` from the files in `src/parking_tickets/cities/`.
Rows and dates are counted live on each portal. Tickets dated in the future are left out;
a few typo dates in the past (such as 1950) remain, so a first date can look too early.

| City | Slug | Rows | First ticket | Last ticket | Source | Last check |
|---|---|---|---|---|---|---|
| Los Angeles | `la` | 26,050,153 | 1950-07-15 | 2026-10-30 | [data.lacity.org](https://data.lacity.org/d/4f5p-udkv) | 2026-11-01 |
| New York City | `nyc` | 182,558,283 | 1970-04-13 | 2026-11-01 | [data.cityofnewyork.us](https://data.cityofnewyork.us/browse?q=parking%20violations%20issued) | 2026-11-01 |
| Philadelphia | `philadelphia` | 9,412,858 | 2012-01-01 | 2017-12-31 | [phl.carto.com](https://opendataphilly.org/datasets/parking-violations/) | 2026-11-01 |
| San Francisco | `sf` | 24,143,146 | 1951-01-21 | 2026-10-29 | [data.sf.gov](https://data.sf.gov/d/ab4h-6ztd) | 2026-11-01 |
