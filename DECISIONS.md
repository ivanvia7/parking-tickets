# Decisions

## 2026-11-02 — Map search, not street text, in map cities
**Decided:** LA, SF and Philadelphia are searched by map click; a later address box only moves the map.
**Why:** one address column with mixed spellings splits counts, and a long street mixes far-apart areas.
**Rules out:** counting by street text outside NYC.

## 2026-11-02 — Address and square size, not map click, in map cities
**Decided:** LA, SF and Philadelphia count inside a square around a typed address; reverses the map-click entry.
**Why:** a typed address finds a place faster than panning.
**Rules out:** map-click counting, address type-ahead.

## 2026-11-02 — Address suggestions from Photon
**Decided:** the address box suggests places while typing through Photon; Nominatim still geocodes typed text on submit. Reverses "address type-ahead" in the entry above.
**Why:** readers expect suggestions; Photon is built for type-ahead, Nominatim forbids it.
**Rules out:** suggestions from ticket addresses, whose spellings do not geocode.

## 2026-11-02 — Point columns read as lat and lon
**Decided:** a city file may name one GeoJSON `point` column instead of `lat` and `lon`; the package splits it and the page counts with `within_box`.
**Why:** Oakland, Winnipeg and Everett publish only a point column.
**Rules out:** new output columns for points.

## 2026-11-02 — Winnipeg fines stay in fine_usd as Canadian dollars
**Decided:** Winnipeg's `full_fine` goes into `fine_usd` unconverted; its city file says `currency = "CAD"` and the page prints CA$.
**Why:** the output columns must not change, and a converted amount is not what the city charges.
**Rules out:** renaming `fine_usd`, currency conversion, the discounted fine.

## 2026-11-02 — Cities skipped in the November search
**Decided:** Cambridge MA, Edmonton, Norfolk, Montgomery County MD and Chicago are not added.
**Why:** no coordinates, no fines, data older than a year, or FOIA only.
**Rules out:** street-only cities beyond NYC for now.

## 2026-11-02 — Newest day must be complete, not just busy
**Decided:** "Last N days" ends on the newest day holding 4/5 of its weekday's usual count, read per day over 4 weeks.
**Why:** LA, SF and NYC upload a day in parts; SF's newest day held 549 of about 5,000.
**Rules out:** one fixed ticket floor for every city.

## 2026-11-02 — Neighbourhood suggestions count as the city
**Decided:** a Photon suggestion whose city equals its district (Sherman Oaks, Hollywood) is kept inside the city's bounds.
**Why:** Photon files some LA addresses under the neighbourhood; towns next door carry no district.
**Rules out:** a hand-kept neighbourhood list, Nominatim calls while typing.

## 2026-11-02 — Page CSV leaves plate numbers out
**Decided:** the page's CSV and row links ask only for the columns the city file names.
**Why:** NYC and SF publish full plate numbers; the README promises none are handed out.
**Rules out:** the portal's whole row via `select *`.
