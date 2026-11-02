// Counts the tickets written around one spot, live from the city portal in the browser.
// The parse half ports the parts of src/parking_tickets/schema.py the page needs;
// tests/test_web.py runs both on the same values and expects the same output.

export const UNGROUPED = "other";

// '904' -> '09:04'; null when the city wrote something unreadable.
export function hmmTime(value) {
  const digits = String(value).padStart(4, "0");
  if (!/^([01]\d|2[0-3])[0-5]\d$/.test(digits)) return null;
  return `${digits.slice(0, 2)}:${digits.slice(2)}`;
}

// '1008P' -> '22:08'; null when the city wrote something unreadable.
export function hhmmpTime(value) {
  const match = /^(\d\d)(\d\d)([AP])$/.exec(String(value)); // hour, minute, A or P
  if (!match || Number(match[1]) > 12 || Number(match[2]) > 59) return null;
  const hour = (Number(match[1]) % 12) + (match[3] === "P" ? 12 : 0);
  return `${String(hour).padStart(2, "0")}:${match[2]}`;
}

// '10:41' or '0:05' -> '00:05'; null when the city wrote something unreadable.
export function hhColonMmTime(value) {
  const match = /^(\d?\d):([0-5]\d)$/.exec(String(value)); // hour, minute
  if (!match || Number(match[1]) > 23) return null;
  return `${match[1].padStart(2, "0")}:${match[2]}`;
}

const TIME_FORMATS = { hmm: hmmTime, hhmmp: hhmmpTime, "hh:mm": hhColonMmTime };

export function clock(city, value) {
  return value == null || value === "" ? null : TIME_FORMATS[city.time_format](value);
}

// Unknown or blank codes land in `other`, never dropped.
export function groupOf(city, code) {
  if (!code) return UNGROUPED;
  return city.groups[String(code).trim()] ?? UNGROUPED;
}

// Raw lat and lon; a point column holds GeoJSON coordinates [lon, lat].
export function coords(city, row) {
  const col = city.columns;
  if (!col.point) return [row[col.lat], row[col.lon]];
  const [lon, lat] = row[col.point]?.coordinates ?? [null, null];
  return [lat, lon];
}

// Portals write 0 for "no location"; points outside the city are geocoding errors.
export function place(city, latRaw, lonRaw) {
  const lat = latRaw == null || latRaw === "" ? null : Number(latRaw);
  const lon = lonRaw == null || lonRaw === "" ? null : Number(lonRaw);
  if (!lat || !lon) return [null, null];
  const bounds = city.bounds;
  if (!bounds) return [lat, lon];
  const latInside = bounds.lat[0] <= lat && lat <= bounds.lat[1];
  const lonInside = bounds.lon[0] <= lon && lon <= bounds.lon[1];
  return latInside && lonInside ? [lat, lon] : [null, null];
}

// NYC fines come from the code table; Manhattan at or below 96th St pays the zone amount.
export function tableFine(city, entry, precinct) {
  const lookup = city.fine_lookup;
  if (!entry) return null;
  const inZone = lookup.zone_values.includes(precinct);
  const amount = entry[inZone ? lookup.zone_amount_field : lookup.amount_field];
  return amount == null || amount === "" ? null : Number(amount);
}

// A NYC day sits in its fiscal-year dataset and the next one; both are read.
export function datasetsFor(city, since, until) {
  if (!city.datasets_by_fiscal_year) return [city.dataset];
  const fiscal = (day) => Number(day.slice(0, 4)) + (Number(day.slice(5, 7)) >= city.fiscal_year_start_month ? 1 : 0);
  const found = [];
  for (let year = fiscal(since); year <= fiscal(until) + 1; year += 1) {
    if (city.datasets_by_fiscal_year[year]) found.push(city.datasets_by_fiscal_year[year]);
  }
  return found;
}
// A square `side` meters wide centered on a spot; a degree of longitude shrinks away from the equator.
const METERS_PER_DEGREE = 111320;

export function square(lat, lon, side) {
  const latHalf = side / 2 / METERS_PER_DEGREE;
  const lonHalf = latHalf / Math.cos((lat * Math.PI) / 180);
  return { lat: [lat - latHalf, lat + latHalf], lon: [lon - lonHalf, lon + lonHalf] };
}


// ---- Page: everything below talks to the portal and the DOM. ----

const DOTS_SHOWN = 500;
const ROW_LIMIT = 50000;
const CENTERS = {
  la: [34.0505, -118.2550], sf: [37.7880, -122.4075], philadelphia: [39.9520, -75.1640],
  oakland: [37.8044, -122.2712], winnipeg: [49.8951, -97.1384], everett: [47.9790, -122.2070],
};
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const HOURS = Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, "0")}:00`);
// Winnipeg fines are Canadian dollars; en-US prints them as CA$.
const money = (city) => new Intl.NumberFormat("en-US", { style: "currency", currency: city.currency ?? "USD", maximumFractionDigits: 0 });
const count = new Intl.NumberFormat("en-US");

const quote = (value) => `'${String(value).replaceAll("'", "''")}'`;
const isoDay = (date) => date.toISOString().slice(0, 10);
const addDays = (day, days) => isoDay(new Date(Date.parse(`${day}T00:00:00Z`) + days * 86400000));

// Cities publish late (NYC about 5 weeks) and upload a day in parts (SF had 549 of about 4,100).
// The newest rows (date index; a 120-day GROUP BY took 59 s cold on SF) find a recent day,
// then a per-day count over the 4 weeks before it picks the newest complete day.
const FULL_DAY_TICKETS = 500; // Everett, about 30 a day, sets its own full_day_tickets
const NEWEST_ROWS = 2000;
const LOOKBACK_DAYS = 120;
const COMPARED_DAYS = 27;
const COMPLETE_SHARE = 0.8;

// Newest day over the floor and at 4/5 of its weekday's median 1 to 3 weeks before.
export function completeDay(city, counts) {
  const floor = city.full_day_tickets ?? FULL_DAY_TICKETS;
  for (const day of Object.keys(counts).sort().reverse()) {
    const earlier = [];
    for (const back of [7, 14, 21]) if (counts[addDays(day, -back)]) earlier.push(counts[addDays(day, -back)]);
    earlier.sort((a, b) => a - b);
    const usual = earlier[Math.floor(earlier.length / 2)] ?? 0; // of two weeks the higher, a holiday is low
    if (counts[day] >= floor && counts[day] >= COMPLETE_SHARE * usual) return day;
  }
  return null;
}

// Tickets per day; a NYC day can come back from two datasets.
async function dayCounts(city, span, q) {
  const counts = {};
  for (const row of await query(city, datasetsFor(city, span.since, span.until), { ...q, where: dayFilter(city, span) })) {
    const day = String(row.day_value).slice(0, 10);
    counts[day] = (counts[day] ?? 0) + Number(row.n ?? 1);
  }
  return counts;
}

async function newestDay(city) {
  if (city.last_day) return city.last_day;
  const until = addDays(isoDay(new Date()), -1);
  const since = addDays(until, -LOOKBACK_DAYS);
  const newestRows = await dayCounts(city, { since, until }, {
    select: `${city.date_field} AS day_value`, order: `${city.date_field} DESC`, limit: NEWEST_ROWS,
  });
  const floorDay = completeDay(city, newestRows);
  if (!floorDay) return until;
  const day = dayOf(city, city.date_field);
  const weeks = await dayCounts(city, { since: addDays(floorDay, -COMPARED_DAYS), until: floorDay }, {
    select: `${day} AS day_value, count(*) AS n`, group: day,
  });
  return completeDay(city, weeks) ?? floorDay;
}

// Days the reader picked, clamped to the city's first and newest day.
function period(city, value) {
  let since;
  let until;
  if (value.startsWith("year:")) {
    const year = value.slice(5);
    [since, until] = [`${year}-01-01`, `${year}-12-31`];
  } else {
    until = city.newest;
    since = addDays(until, 1 - Number(value));
  }
  if (since < city.first_day) since = city.first_day;
  if (city.last_day && until > city.last_day) until = city.last_day;
  return { since, until };
}

const hourOf = (city, field) => (city.portal === "carto" ? `extract(hour from ${field})` : `date_extract_hh(${field})`);
const dowOf = (city, field) => (city.portal === "carto" ? `extract(dow from ${field})` : `date_extract_dow(${field})`);
const dayOf = (city, field) => (city.portal === "carto" ? `date_trunc('day', ${field})` : `date_trunc_ymd(${field})`);

function portalUrl(city, dataset, q) {
  if (city.portal === "carto") {
    const sql = [`SELECT ${q.select} FROM ${dataset} WHERE ${q.where}`,
      q.group && `GROUP BY ${q.group}`, q.order && `ORDER BY ${q.order}`, `LIMIT ${q.limit ?? ROW_LIMIT}`];
    const url = new URL(`https://${city.host}/api/v2/sql`);
    url.searchParams.set("q", sql.filter(Boolean).join(" "));
    return url;
  }
  const url = new URL(`https://${city.host}/resource/${dataset}.json`);
  const params = { $select: q.select, $where: q.where, $group: q.group, $order: q.order, $limit: String(q.limit ?? ROW_LIMIT) };
  for (const [key, value] of Object.entries(params)) if (value) url.searchParams.set(key, value);
  return url;
}

// One request at a time, like the CLI; a NYC period can touch several datasets.
async function query(city, datasets, q) {
  const rows = [];
  for (const dataset of datasets) {
    const response = await fetch(portalUrl(city, dataset, q));
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${response.status} from ${city.host}: ${text.slice(0, 200)}`);
    }
    const body = await response.json();
    rows.push(...(city.portal === "carto" ? body.rows : body));
  }
  return rows;
}

function spotFilter(city, spot) {
  if (spot.wholeCity) return null;
  if (spot.street) {
    const [house, street] = city.columns.location;
    const where = [`upper(${street}) = ${quote(spot.street.toUpperCase())}`];
    if (spot.house) where.push(`${house} = ${quote(spot.house)}`);
    return where.join(" AND ");
  }
  const { lat, lon, point } = city.columns;
  const { box } = spot;
  if (point) return `within_box(${point}, ${box.lat[1]}, ${box.lon[0]}, ${box.lat[0]}, ${box.lon[1]})`;
  return `${lat} between ${box.lat[0]} and ${box.lat[1]} AND ${lon} between ${box.lon[0]} and ${box.lon[1]}`;
}

function dayFilter(city, { since, until }) {
  const field = city.date_field;
  return `${field} >= '${since}T00:00:00' AND ${field} < '${addDays(until, 1)}T00:00:00'`;
}

let codeTable = null;
async function fineTable(city) {
  const lookup = city.fine_lookup;
  if (!codeTable) {
    const rows = await query({ ...city, portal: "socrata", host: lookup.host }, [lookup.dataset], { select: "*" });
    codeTable = {};
    for (const row of rows) codeTable[row[lookup.code_field]] = row;
  }
  return codeTable;
}

// Ticket count, fines and groups from a server-side GROUP BY; no rows are downloaded.
async function byGroup(city, datasets, where) {
  const codeColumn = city.group_column;
  const precinct = city.fine_lookup?.zone_field;
  const select = [`${codeColumn} AS code_value`, "count(*) AS n"];
  if (city.columns.fine_usd) select.push(`sum(${city.columns.fine_usd}) AS fine_total`);
  const groupBy = precinct ? `${codeColumn}, ${precinct}` : codeColumn;
  if (precinct) select.push(`${precinct} AS precinct_value`);
  const rows = await query(city, datasets, { select: select.join(", "), where, group: groupBy });
  const fines = city.fine_lookup ? await fineTable(city) : null;
  const groups = new Map();
  let tickets = 0;
  let total = 0;
  let noFine = 0;
  for (const row of rows) {
    const n = Number(row.n);
    const each = fines ? tableFine(city, fines[row.code_value], row.precinct_value) : null;
    if (fines && each == null) noFine += n;
    const fine = fines ? (each ?? 0) * n : Number(row.fine_total ?? 0);
    const group = groupOf(city, row.code_value);
    groups.set(group, (groups.get(group) ?? 0) + n);
    tickets += n;
    total += fine;
  }
  const ranked = [...groups].sort((a, b) => b[1] - a[1]);
  const top = ranked.slice(0, 5);
  return { tickets, total, noFine, top };
}

async function byHour(city, datasets, where) {
  if (city.midnight_is_day_only) return null; // the day only, so no hours to count
  const hours = Array(24).fill(0);
  if (city.time_field) { // time is a text column; read each value once and bucket it here
    const rows = await query(city, datasets, {
      select: `${city.time_field} AS time_value, count(*) AS n`, where, group: city.time_field,
    });
    for (const row of rows) {
      const time = clock(city, row.time_value);
      if (time) hours[Number(time.slice(0, 2))] += Number(row.n);
    }
    return hours;
  }
  const expr = hourOf(city, city.date_field);
  for (const row of await query(city, datasets, { select: `${expr} AS hour_value, count(*) AS n`, where, group: expr })) {
    hours[Number(row.hour_value)] += Number(row.n);
  }
  return hours;
}

async function byWeekday(city, datasets, where) {
  const days = Array(7).fill(0);
  const expr = dowOf(city, city.date_field);
  for (const row of await query(city, datasets, { select: `${expr} AS dow_value, count(*) AS n`, where, group: expr })) {
    days[Number(row.dow_value)] += Number(row.n);
  }
  return days;
}

async function newestTickets(city, datasets, where) {
  const col = city.columns;
  const wanted = [col.source_id, city.date_field, city.time_field, col.violation_text, col.fine_usd, col.lat, col.lon, col.point, col.location];
  const rows = await query(city, datasets, {
    // Winnipeg's code and text share a column; ask for each column once.
    select: [...new Set(wanted.filter(Boolean))].join(", "), where, order: `${city.date_field} DESC`, limit: DOTS_SHOWN,
  });
  return rows.map((row) => {
    const [lat, lon] = place(city, ...coords(city, row));
    return { row, lat, lon };
  }).filter((dot) => dot.lat != null);
}

// The portal's own CSV of every ticket counted; one file per dataset (NYC can touch two).
function csvUrl(city, dataset, where) {
  const url = portalUrl(city, dataset, { select: "*", where, order: `${city.date_field} DESC` });
  if (city.portal === "carto") {
    url.searchParams.set("format", "csv");
    url.searchParams.set("filename", `parking-tickets-${city.slug}`);
  } else {
    url.pathname = url.pathname.replace(/\.json$/, ".csv"); // same query, CSV body
  }
  return url;
}

// Fetch and save one CSV; a NYC period can need two datasets, joined under one header.
async function saveCsv(city, datasets, where, name) {
  const parts = [];
  for (const dataset of datasets) {
    const response = await fetch(csvUrl(city, dataset, where));
    if (!response.ok) throw new Error(`${response.status} from ${city.host}`);
    const text = await response.text();
    parts.push(parts.length ? text.slice(text.indexOf("\n") + 1) : text);
  }
  const link = el("a", { href: URL.createObjectURL(new Blob(parts, { type: "text/csv" })), download: name });
  link.click();
  URL.revokeObjectURL(link.href);
}

function csvButton(city, { span, datasets, where, tickets }) {
  const name = `parking-tickets-${city.slug}-${span.since}-to-${span.until}.csv`;
  const button = el("button", { type: "button", className: "ghost", textContent: "Download CSV" });
  button.onclick = async () => {
    button.disabled = true;
    button.textContent = "Downloading...";
    try {
      await saveCsv(city, datasets, where, name);
      button.textContent = "Download CSV";
    } catch (error) {
      button.textContent = `Download failed: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  };
  const capped = tickets > ROW_LIMIT ? ` Only the newest ${count.format(ROW_LIMIT)} per file.` : "";
  return el("p", {}, button, ` The city's own rows for these ${count.format(tickets)} tickets.${capped}`);
}

// The portal's own row, so a reader can check the source.
function rowUrl(city, dataset, id) {
  return portalUrl(city, dataset, { select: "*", where: `${city.columns.source_id} = ${quote(id)}`, limit: 1 });
}

// A DOM node; text goes in as text nodes, so portal data never becomes HTML.
function el(tag, attrs = {}, ...children) {
  const node = Object.assign(document.createElement(tag), attrs);
  for (const child of children) if (child != null) node.append(child);
  return node;
}

function bars(labels, values, format) {
  const most = Math.max(1, ...values);
  return el("div", { className: "bars" }, ...labels.flatMap((label, index) => [
    el("span", { textContent: label }),
    el("i", { style: `width: ${(100 * values[index]) / most}%` }),
    el("b", { textContent: format(values[index]) }),
  ]));
}

const page = {};

function dotPopup(city, dataset, { row }) {
  const col = city.columns;
  const stamp = String(row[city.date_field]);
  const dayOnly = city.midnight_is_day_only && stamp.slice(11, 19) === "00:00:00";
  const time = city.time_field ? clock(city, row[city.time_field]) : dayOnly ? null : stamp.slice(11, 16);
  const fine = row[col.fine_usd];
  return el("div", {},
    el("strong", { textContent: `${String(row[city.date_field]).slice(0, 10)} ${time ?? ""}` }), el("br"),
    row[col.violation_text] ?? "", el("br"),
    fine == null ? "" : money(city).format(Number(fine)), " ",
    row[col.location] ?? "", el("br"),
    el("a", { href: rowUrl(city, dataset, row[col.source_id]), target: "_blank", rel: "noopener", textContent: "source" }));
}

// Called after each step; hours and weekdays stay out until they arrive.
function render(city, spotLabel, span, result) {
  const { tickets, total, noFine, top } = result.groups;
  const hourChart = result.hours
    ? [el("h3", { textContent: "By hour of day" }), bars(HOURS, result.hours, count.format)]
    : [el("p", { textContent: `${city.name} publishes the day of each ticket, not the time, so there is no hour chart.` })];
  const timing = result.days
    ? [...hourChart, el("h3", { textContent: "By weekday" }), bars(WEEKDAYS, result.days, count.format)]
    : [el("h3", { textContent: "Reading hours and weekdays..." })];
  const hasFines = Boolean(city.columns.fine_usd || city.fine_lookup);
  page.answer.querySelector("h2").replaceChildren(spotLabel, " ",
    el("small", { textContent: `${span.since} to ${span.until}` }));
  const label = (group) => group.replaceAll("_", " ");
  page.answer.querySelector(".body").replaceChildren(
    el("div", { className: "totals" },
      el("div", {}, count.format(tickets), el("small", { textContent: "tickets" })),
      hasFines ? el("div", {}, money(city).format(total), el("small", { textContent: "total fines" })) : null),
    el("h3", { textContent: "Top groups" }),
    bars(top.map(([group]) => label(group)), top.map(([, n]) => n),
      (n) => `${Math.round((100 * n) / Math.max(1, tickets))}%`),
    ...timing);
  const notes = [`Read live from ${city.host}, the same rows parking-tickets fetch reads.`];
  if (noFine) notes.push(`${count.format(noFine)} tickets have a code without a fine and add no money.`);
  if (city.last_day) notes.push(`${city.name} data stops ${city.last_day}.`);
  if (!hasFines) notes.push(`${city.name} publishes no fine amounts.`);
  if (city.currency) notes.push(`Fines in ${city.currency}.`);
  page.answer.querySelector(".note").textContent = notes.join(" ");
  page.answer.hidden = false;
}

async function countSpot(spot, spotLabel) {
  if (page.running) return;
  const city = page.cities[page.form.city.value];
  if (!city.newest) return; // pickCity is still finding the newest day
  const span = period(city, page.form.period.value);
  const datasets = datasetsFor(city, span.since, span.until);
  const where = [dayFilter(city, span), spotFilter(city, spot)].filter(Boolean).join(" AND ");
  setBusy(true);
  page.dots.clearLayers();
  const started = performance.now();
  const steps = spot.street ? 3 : 4;
  try {
    page.status.textContent = `Step 1 of ${steps}: counting tickets and fines, ${span.since} to ${span.until}...`;
    const groups = await byGroup(city, datasets, where);
    render(city, spotLabel, span, { groups });
    page.answer.classList.remove("loading");
    page.status.textContent = `Step 2 of ${steps}: reading hours of day...`;
    const hours = await byHour(city, datasets, where);
    page.status.textContent = `Step 3 of ${steps}: reading weekdays...`;
    const days = await byWeekday(city, datasets, where);
    render(city, spotLabel, span, { groups, hours, days });
    if (groups.tickets) page.answer.querySelector(".body").append(csvButton(city, { span, datasets, where, tickets: groups.tickets }));
    if (!spot.street) {
      page.status.textContent = `Step 4 of ${steps}: placing the newest tickets on the map...`;
      for (const dot of await newestTickets(city, [datasets.at(-1)], where)) {
        L.circleMarker([dot.lat, dot.lon], { radius: 5, color: "#fff", weight: 1.5, fillColor: "#ff3b45", fillOpacity: 1 })
          .bindPopup(() => dotPopup(city, datasets.at(-1), dot)).addTo(page.dots);
      }
    }
    const seconds = ((performance.now() - started) / 1000).toFixed(1);
    const exactMiss = spot.house && groups.tickets === 0
      ? " None at that exact house number; pick one from the list or try the street alone."
      : "";
    page.status.textContent = `${count.format(groups.tickets)} tickets, read in ${seconds} s.${exactMiss}`;
  } catch (error) {
    page.status.textContent = `The city portal did not answer: ${error.message}`;
  } finally {
    setBusy(false);
  }
}

// NYC publishes no coordinates, so it is searched by street and house number instead of an address square.
const searchesByStreet = (city) => !city.columns.lat && !city.columns.point;

// Progress bar, dimmed old answer, pulsing box and a locked form while the portal works.
function setBusy(on) {
  page.running = on;
  page.progress.hidden = !on;
  page.answer.classList.toggle("loading", on);
  page.box.getElement()?.classList.toggle("box-searching", on);
  page.searchButton.textContent = on ? "Counting..." : "Count tickets";
  page.form.querySelectorAll("button").forEach((button) => { button.disabled = on; });
}

// Street and house suggestions come from the city's own tickets, busiest first.
const SUGGESTIONS = 8;
const SUGGEST_DAYS = 7;
const TYPE_PAUSE_MS = 250;
let suggestTurn = 0;

async function suggest(city, { list, select, where, days, keep }) {
  const turn = ++suggestTurn; // a slower, older answer must not overwrite a newer one
  const span = { since: addDays(city.newest, 1 - days), until: city.newest };
  const rows = await query(city, datasetsFor(city, span.since, span.until), {
    select: `${select} AS value, count(*) AS n`, where: `${dayFilter(city, span)} AND ${where}`,
    group: select, order: "n DESC", limit: SUGGESTIONS * 4,
  });
  if (turn !== suggestTurn) return;
  const counts = new Map(); // a NYC day can come back from two datasets
  for (const row of rows) {
    if (keep(row.value)) counts.set(row.value, (counts.get(row.value) ?? 0) + Number(row.n));
  }
  const ranked = [...counts].sort((a, b) => b[1] - a[1]);
  const options = ranked.slice(0, SUGGESTIONS).map(([value, n]) =>
    el("option", { value, label: `${count.format(n)} tickets in ${days} days` }));
  list.replaceChildren(...options);
}

function suggestStreets() {
  clearTimeout(page.typing);
  const city = page.cities[page.form.city.value];
  const typed = page.form.street.value.trim().toUpperCase();
  if (typed.length < 2 || !city.newest || !searchesByStreet(city)) return;
  const street = `upper(${city.columns.location[1]})`;
  page.typing = setTimeout(() => {
    const startsWith = quote(`${typed}%`);
    const where = `${street} like ${startsWith}`;
    suggest(city, { list: page.streetList, select: street, where, days: SUGGEST_DAYS, keep: Boolean })
      .catch((error) => console.warn("street suggestions failed:", error.message)); // the count still works
  }, TYPE_PAUSE_MS);
}

function suggestHouses() {
  const city = page.cities[page.form.city.value];
  const typed = page.form.street.value.trim().toUpperCase();
  page.houseList.replaceChildren();
  if (!typed || !city.newest || !searchesByStreet(city)) return;
  const [house, street] = city.columns.location;
  const isNumber = (value) => /^\d/.test(value ?? ""); // NYC also writes E, W or N here
  const where = `upper(${street}) = ${quote(typed)}`;
  suggest(city, { list: page.houseList, select: house, where, days: 30, keep: isNumber })
    .catch((error) => console.warn("house suggestions failed:", error.message));
}

// Every ticket of the period, also those without a map spot; the map shows the whole city.
function countWholeCity(city) {
  page.box.remove();
  const { lat, lon } = city.bounds;
  page.map.fitBounds([[lat[0], lon[0]], [lat[1], lon[1]]]);
  countSpot({ wholeCity: true }, `All of ${city.name}`);
}

// Draws the square the reader asked for, fits the map to it and counts inside it.
function countSquare(city, lat, lon, label) {
  if (page.form.size.value === "city") {
    countWholeCity(city);
    return;
  }
  if (place(city, lat, lon)[0] == null) {
    page.status.textContent = `That spot is outside ${city.name}.`;
    return;
  }
  const box = square(lat, lon, Number(page.form.size.value));
  page.box.setBounds([[box.lat[0], box.lon[0]], [box.lat[1], box.lon[1]]]);
  page.box.addTo(page.map);
  page.map.fitBounds(page.box.getBounds());
  countSpot({ box }, `${page.form.size.selectedOptions[0].textContent} square at ${label}`);
}

// OpenStreetMap Nominatim, limited to the city's bounds. Its usage policy allows
// 1 request a second and no type-ahead, so it runs only when the reader submits.
const GEOCODER = "https://nominatim.openstreetmap.org/search";
const GEOCODE_GAP_MS = 1000;
let lastGeocode = 0;

async function geocode(city, address) {
  const wait = lastGeocode + GEOCODE_GAP_MS - Date.now();
  if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
  lastGeocode = Date.now();
  const { lat, lon } = city.bounds;
  const url = new URL(GEOCODER);
  url.search = new URLSearchParams({
    format: "jsonv2", limit: "1", q: address, viewbox: `${lon[0]},${lat[1]},${lon[1]},${lat[0]}`, bounded: "1",
    addressdetails: "1",
  });
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} from ${url.host}`);
  const [found] = await response.json();
  if (!found) return null;
  // The bounds also cover towns next door, e.g. 600 S Broadway lands in Redondo Beach.
  const inCity = found.address.city === city.name;
  return { lat: Number(found.lat), lon: Number(found.lon), name: found.display_name, inCity };
}

// Address suggestions while typing come from Photon, an OpenStreetMap search built for type-ahead;
// Nominatim forbids that. A picked suggestion keeps its coordinates, so submit skips Nominatim.
const SUGGESTER = "https://photon.komoot.io/api/";
const ADDRESS_MIN_CHARS = 3;
let addressTurn = 0;

function suggestAddresses() {
  clearTimeout(page.addressTyping);
  const city = page.cities[page.form.city.value];
  const typed = page.form.address.value.trim();
  if (typed.length < ADDRESS_MIN_CHARS || searchesByStreet(city) || page.places.has(typed)) return;
  page.addressTyping = setTimeout(async () => {
    const turn = ++addressTurn; // a slower, older answer must not overwrite a newer one
    const { lat, lon } = city.bounds;
    const url = new URL(SUGGESTER);
    url.search = new URLSearchParams({ q: typed, limit: String(SUGGESTIONS), bbox: `${lon[0]},${lat[0]},${lon[1]},${lat[1]}` });
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`${response.status} from ${url.host}`);
      const { features } = await response.json();
      if (turn !== addressTurn) return;
      const options = [];
      for (const { properties: found, geometry } of features) {
        if (found.city !== city.name) continue; // the bounds also cover towns next door
        const street = [found.housenumber, found.street].filter(Boolean).join(" ");
        const label = [found.name, street, found.district ?? found.postcode].filter(Boolean).join(", ");
        if (page.places.has(label)) continue;
        page.places.set(label, { lon: geometry.coordinates[0], lat: geometry.coordinates[1] });
        options.push(el("option", { value: label }));
      }
      page.addressList.replaceChildren(...options);
    } catch (error) {
      console.warn("address suggestions failed:", error.message); // submit still geocodes
    }
  }, TYPE_PAUSE_MS);
}

async function countAddress(city) {
  const address = page.form.address.value.trim();
  if (!address) {
    page.status.textContent = "Type an address.";
    return;
  }
  const picked = page.places.get(address);
  if (picked) {
    countSquare(city, picked.lat, picked.lon, address);
    return;
  }
  setBusy(true);
  page.status.textContent = `Finding ${address} in ${city.name}...`;
  let found;
  try {
    found = await geocode(city, address);
  } catch (error) {
    page.status.textContent = `The address lookup did not answer: ${error.message}`;
    return;
  } finally {
    setBusy(false);
  }
  if (page.form.city.value !== city.slug) return; // the reader switched city while we waited
  if (!found) {
    page.status.textContent = `No address "${address}" found in ${city.name}; nothing counted.`;
    return;
  }
  const short = found.name.split(", ").slice(0, 3).join(", "); // the full name runs to county and country
  if (!found.inCity) {
    page.status.textContent = `The closest match, ${short}, is outside ${city.name}; nothing counted.`;
    return;
  }
  countSquare(city, found.lat, found.lon, short);
}

function search(event) {
  event.preventDefault();
  if (page.running) return;
  const city = page.cities[page.form.city.value];
  if (searchesByStreet(city)) countStreet();
  else if (page.form.size.value === "city") countWholeCity(city);
  else countAddress(city);
}

function countStreet() {
  const street = page.form.street.value.trim();
  const house = page.form.house.value.trim();
  if (!street) {
    page.status.textContent = "Type a street name.";
    return;
  }
  countSpot({ street, house }, [house, street.toUpperCase()].filter(Boolean).join(" "));
}

function useLocation() {
  page.status.textContent = "Asking the browser for your location...";
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      countSquare(page.cities[page.form.city.value], coords.latitude, coords.longitude, "your location");
    },
    (error) => { page.status.textContent = `No location: ${error.message}`; },
  );
}

async function pickCity() {
  const slug = page.form.city.value;
  const city = page.cities[slug];
  const isStreet = searchesByStreet(city);
  page.form.address.value = "";
  page.addressList.replaceChildren();
  page.places.clear();
  page.form.street.value = "";
  page.form.house.value = "";
  page.streetList.replaceChildren();
  page.houseList.replaceChildren();
  const options = city.last_day
    ? [2017, 2016, 2015, 2014, 2013, 2012].map((year) => [`year:${year}`, String(year)])
    : [["30", "Last 30 days"], ["90", "Last 90 days"], ["365", "Last 365 days"]];
  page.form.period.replaceChildren(...options.map(([value, text]) => el("option", { value, textContent: text })));
  page.map.getContainer().hidden = isStreet;
  page.addressBox.hidden = isStreet;
  page.streetBox.hidden = !isStreet;
  page.nearButton.hidden = isStreet;
  page.answer.hidden = true;
  page.dots.clearLayers();
  page.box.remove();
  if (!isStreet) {
    page.map.invalidateSize();
    page.map.setView(CENTERS[slug], 16);
  }
  if (!city.newest) {
    page.status.textContent = `Finding the newest day ${city.name} has published...`;
    page.progress.hidden = false;
    try {
      city.newest = await newestDay(city);
    } catch (error) {
      page.status.textContent = `The city portal did not answer: ${error.message}`;
      return;
    } finally {
      page.progress.hidden = true;
    }
  }
  if (page.form.city.value !== slug) return; // the reader switched city while we waited
  const action = isStreet
    ? `${city.name} tickets carry no coordinates, so no square can hold them; type a street.`
    : "Type an address and pick a square size to count the tickets inside it.";
  const covers = city.last_day ? `${city.name} data covers 2012 to 2017 only.` : `Newest ${city.name} data: ${city.newest}.`;
  page.status.textContent = `${action} ${covers}`;
}

// "Type an address in Everett, Los Angeles, or Oakland, or a street in New York City, ..." from cities.json.
export function leadLine(cities) {
  const names = (street) => new Intl.ListFormat("en", { type: "disjunction" })
    .format(cities.filter((city) => searchesByStreet(city) === street).map((city) => city.name));
  const streets = cities.some(searchesByStreet) ? `, or a street in ${names(true)}` : "";
  return `Type an address in ${names(false)}${streets}, and see what tickets get written there, when, and for how much.`;
}

async function start() {
  const response = await fetch("cities.json");
  page.cities = await response.json();
  for (const id of ["form", "status", "answer", "nearButton", "addressBox", "streetBox", "searchButton", "progress", "addressList", "streetList", "houseList", "lead"]) {
    page[id] = document.getElementById(id);
  }
  page.map = L.map("map");
  // CARTO's dark tiles now need an API key; OSM tiles need none and are darkened in CSS.
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(page.map);
  page.dots = L.layerGroup().addTo(page.map);
  page.places = new Map(); // suggested address label -> its coordinates
  page.box = L.rectangle([[0, 0], [0, 0]], { color: "#78a9ff", weight: 1, fillOpacity: 0.1 });
  for (const [slug, city] of Object.entries(page.cities)) {
    page.form.city.append(el("option", { value: slug, textContent: city.name }));
  }
  page.lead.textContent = leadLine(Object.values(page.cities));
  page.form.city.value = "la";
  page.form.city.addEventListener("change", pickCity);
  page.form.addEventListener("submit", search);
  page.form.address.addEventListener("input", suggestAddresses);
  page.form.street.addEventListener("input", suggestStreets);
  page.form.street.addEventListener("change", suggestHouses);
  page.nearButton.addEventListener("click", useLocation);
  pickCity();
}

if (globalThis.document) start();
