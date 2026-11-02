# Decisions

## 2026-11-02 — Map search, not street text, in map cities
**Decided:** LA, SF and Philadelphia are searched by map click; a later address box only moves the map.
**Why:** one address column with mixed spellings splits counts, and a long street mixes far-apart areas.
**Rules out:** counting by street text outside NYC.

## 2026-11-02 — Address and square size, not map click, in map cities
**Decided:** LA, SF and Philadelphia count inside a square around a typed address; reverses the map-click entry.
**Why:** a typed address finds a place faster than panning.
**Rules out:** map-click counting, address type-ahead.
