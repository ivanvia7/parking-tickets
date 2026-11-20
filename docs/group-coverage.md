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

Winnipeg has used several code spellings. Codes like `01Meter Expired` and `M06-No Stop` now
group like their current twins: 2017 is 88.5% outside `other`. Codes with a space after the
number, such as `01 2011 Parked -meter expi` and `07 No stopping anytime` (2012 to about 2016),
have no mapping yet: 2014 is 0.0% outside `other`. Of 1,905,868 Winnipeg tickets from 2012 to
2026, 816,685 remain in `other`: 682,097 in that spelling and 123,762 under snow-route and
`RPB Zone` codes, which have no group row.
