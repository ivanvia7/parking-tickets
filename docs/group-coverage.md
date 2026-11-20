# Group coverage on held-out months

Share of each city's tickets that `groups.csv` places outside `other`, on a month the
groups were not tuned on (they were tuned on June 2025; Philadelphia June 2017).
Each row is `uv run python scripts/group_coverage.py <slug> <first day> <last day>`, run 2026-11-20.

| City | Month | Outside `other` |
|---|---|---|
| Buffalo | 2025-10 | 94.6% |
| Washington | 2025-10 | 95.2% |
| Everett | 2025-10 | 100.0% |
| Los Angeles | 2025-10 | 96.4% |
| New York City | 2025-10 | 97.8% |
| Oakland | 2025-10 | 97.5% |
| Philadelphia | 2016-10 | 98.1% |
| San Francisco | 2025-10 | 95.8% |
| Syracuse | 2025-10 | 95.2% |
| Winnipeg | 2025-10 | 99.9% |

Buffalo's biggest misses are `PARKING WITHOUT CONSENT (ALL)` (251 tickets) and
`PERSISTEN VIOLATORS AND SCOFFLAWS` (75); they stay in `other` here so this month remains a fair test.

## Known gap: Winnipeg before 2018

Winnipeg changed its code spelling twice. Codes like `01Meter Expired` (to about 2018) now
group like their `P01Meter Expired` twins: 2017 is 85.6% outside `other`. Codes like
`01 2011 Parked -meter expi` (2012 to about 2016) have no mapping yet: 2014 is 0.0% outside
`other`. Across 2012 to 2026, about 820,000 Winnipeg tickets remain in `other`, most of them
in this spelling; `P39Snow Route` and the `RPB Zone` codes make up most of the rest.
