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
