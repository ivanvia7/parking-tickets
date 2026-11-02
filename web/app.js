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

const TIME_FORMATS = { hmm: hmmTime, hhmmp: hhmmpTime };

export function clock(city, value) {
  return value == null || value === "" ? null : TIME_FORMATS[city.time_format](value);
}

// Unknown or blank codes land in `other`, never dropped.
export function groupOf(city, code) {
  if (!code) return UNGROUPED;
  return city.groups[String(code).trim()] ?? UNGROUPED;
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


// ---- Page: everything below talks to the portal and the DOM. ----

// About 300 m wide around the clicked spot.
const HALF_BOX_DEGREES = 0.00135;
const DOTS_SHOWN = 500;
const ROW_LIMIT = 50000;
const CENTERS = { la: [34.0505, -118.2550], sf: [37.7880, -122.4075], philadelphia: [39.9520, -75.1640] };
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const HOURS = Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, "0")}:00`);
const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const count = new Intl.NumberFormat("en-US");

const quote = (value) => `'${String(value).replaceAll("'", "''")}'`;
const isoDay = (date) => date.toISOString().slice(0, 10);
const addDays = (day, days) => isoDay(new Date(Date.parse(`${day}T00:00:00Z`) + days * 86400000));

// Cities publish late (NYC about 5 weeks) and keep a few stray late or typo rows,
// so a period ends on the newest day that holds a full day's tickets among the newest rows.
// Reading the newest rows uses the portal's date index; a per-day GROUP BY took 59 s cold on SF.
const FULL_DAY_TICKETS = 500;
const NEWEST_ROWS = 2000;
const LOOKBACK_DAYS = 120;

async function newestDay(city) {
  if (city.last_day) return city.last_day;
  const until = addDays(isoDay(new Date()), -1);
  const since = addDays(until, -LOOKBACK_DAYS);
  const rows = await query(city, datasetsFor(city, since, until), {
    select: `${city.date_field} AS day_value`, where: dayFilter(city, { since, until }),
    order: `${city.date_field} DESC`, limit: NEWEST_ROWS,
  });
  const perDay = new Map(); // a NYC day can come back from two datasets
  for (const row of rows) {
    const day = String(row.day_value).slice(0, 10);
    perDay.set(day, (perDay.get(day) ?? 0) + 1);
  }
  let newest = null;
  for (const [day, n] of perDay) if (n >= FULL_DAY_TICKETS && (newest == null || day > newest)) newest = day;
  return newest ?? until;
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
  if (spot.street) {
    const [house, street] = city.columns.location;
    const where = [`upper(${street}) = ${quote(spot.street.toUpperCase())}`];
    if (spot.house) where.push(`${house} = ${quote(spot.house)}`);
    return where.join(" AND ");
  }
  const lonHalf = HALF_BOX_DEGREES / Math.cos((spot.lat * Math.PI) / 180);
  const { lat, lon } = city.columns;
  return `${lat} between ${spot.lat - HALF_BOX_DEGREES} and ${spot.lat + HALF_BOX_DEGREES}`
    + ` AND ${lon} between ${spot.lon - lonHalf} and ${spot.lon + lonHalf}`;
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
  const wanted = [col.source_id, city.date_field, city.time_field, col.violation_text, col.fine_usd, col.lat, col.lon, col.location];
  const rows = await query(city, datasets, {
    select: wanted.filter(Boolean).join(", "), where, order: `${city.date_field} DESC`, limit: DOTS_SHOWN,
  });
  return rows.map((row) => {
    const [lat, lon] = place(city, row[col.lat], row[col.lon]);
    return { row, lat, lon };
  }).filter((dot) => dot.lat != null);
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
  const time = city.time_field ? clock(city, row[city.time_field]) : String(row[city.date_field]).slice(11, 16);
  const fine = row[col.fine_usd];
  return el("div", {},
    el("strong", { textContent: `${String(row[city.date_field]).slice(0, 10)} ${time ?? ""}` }), el("br"),
    row[col.violation_text] ?? "", el("br"),
    fine == null ? "" : usd.format(Number(fine)), " ",
    row[col.location] ?? "", el("br"),
    el("a", { href: rowUrl(city, dataset, row[col.source_id]), target: "_blank", rel: "noopener", textContent: "source" }));
}

// Called after each step; hours and weekdays stay out until they arrive.
function render(city, spotLabel, span, result) {
  const { tickets, total, noFine, top } = result.groups;
  const timing = result.hours
    ? [el("h3", { textContent: "By hour of day" }), bars(HOURS, result.hours, count.format),
      el("h3", { textContent: "By weekday" }), bars(WEEKDAYS, result.days, count.format)]
    : [el("h3", { textContent: "Reading hours and weekdays..." })];
  page.answer.querySelector("h2").replaceChildren(spotLabel, " ",
    el("small", { textContent: `${span.since} to ${span.until}` }));
  const label = (group) => group.replaceAll("_", " ");
  page.answer.querySelector(".body").replaceChildren(
    el("div", { className: "totals" },
      el("div", {}, count.format(tickets), el("small", { textContent: "tickets" })),
      el("div", {}, usd.format(total), el("small", { textContent: "total fines" }))),
    el("h3", { textContent: "Top groups" }),
    bars(top.map(([group]) => label(group)), top.map(([, n]) => n),
      (n) => `${Math.round((100 * n) / Math.max(1, tickets))}%`),
    ...timing);
  const notes = [`Read live from ${city.host}, the same rows parking-tickets fetch reads.`];
  if (noFine) notes.push(`${count.format(noFine)} tickets have a code without a fine and add no money.`);
  if (city.last_day) notes.push(`${city.name} data stops ${city.last_day}.`);
  page.answer.querySelector(".note").textContent = notes.join(" ");
  page.answer.hidden = false;
}

async function countSpot(spot, spotLabel) {
  if (page.running) return;
  const city = page.cities[page.form.city.value];
  if (!city.newest) return; // pickCity is still finding the newest day
  const span = period(city, page.form.period.value);
  const datasets = datasetsFor(city, span.since, span.until);
  const where = `${dayFilter(city, span)} AND ${spotFilter(city, spot)}`;
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

// NYC publishes no coordinates, so it is searched by street and house number instead of the map.
const searchesByStreet = (city) => !city.columns.lat;

// Progress bar, dimmed old answer, pulsing box and a locked form while the portal works.
function setBusy(on) {
  page.running = on;
  page.progress.hidden = !on;
  page.answer.classList.toggle("loading", on);
  page.box.getElement()?.classList.toggle("box-searching", on);
  page.streetButton.textContent = on ? "Counting..." : "Count tickets";
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

function clickMap(event) {
  const city = page.cities[page.form.city.value];
  const { lat, lng } = event.latlng;
  if (place(city, lat, lng)[0] == null) {
    page.status.textContent = `That spot is outside ${city.name}.`;
    return;
  }
  const lonHalf = HALF_BOX_DEGREES / Math.cos((lat * Math.PI) / 180);
  page.box.setBounds([[lat - HALF_BOX_DEGREES, lng - lonHalf], [lat + HALF_BOX_DEGREES, lng + lonHalf]]);
  page.box.addTo(page.map);
  document.getElementById("mapHint").hidden = true;
  countSpot({ lat, lon: lng }, `Spot at ${lat.toFixed(4)}, ${lng.toFixed(4)}`);
}

function countStreet(event) {
  event.preventDefault();
  if (!searchesByStreet(page.cities[page.form.city.value])) return; // map cities count on click
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
      page.map.setView([coords.latitude, coords.longitude], 17);
      clickMap({ latlng: { lat: coords.latitude, lng: coords.longitude } });
    },
    (error) => { page.status.textContent = `No location: ${error.message}`; },
  );
}

async function pickCity() {
  const slug = page.form.city.value;
  const city = page.cities[slug];
  const isStreet = searchesByStreet(city);
  page.form.street.value = "";
  page.form.house.value = "";
  page.streetList.replaceChildren();
  page.houseList.replaceChildren();
  const options = city.last_day
    ? [2017, 2016, 2015, 2014, 2013, 2012].map((year) => [`year:${year}`, String(year)])
    : [["30", "Last 30 days"], ["90", "Last 90 days"], ["365", "Last 365 days"]];
  page.form.period.replaceChildren(...options.map(([value, text]) => el("option", { value, textContent: text })));
  page.map.getContainer().hidden = isStreet;
  page.streetBox.hidden = !isStreet;
  page.streetButton.hidden = !isStreet;
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
    ? `${city.name} publishes no coordinates; type a street.`
    : "Click a spot on the map to count tickets in a box about 300 m wide.";
  const covers = city.last_day ? `${city.name} data covers 2012 to 2017 only.` : `Newest ${city.name} data: ${city.newest}.`;
  page.status.textContent = `${action} ${covers}`;
}

async function start() {
  const response = await fetch("cities.json");
  page.cities = await response.json();
  for (const id of ["form", "status", "answer", "nearButton", "streetBox", "streetButton", "progress", "streetList", "houseList"]) {
    page[id] = document.getElementById(id);
  }
  page.map = L.map("map");
  // CARTO's dark tiles now need an API key; OSM tiles need none and are darkened in CSS.
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(page.map);
  page.dots = L.layerGroup().addTo(page.map);
  page.box = L.rectangle([[0, 0], [0, 0]], { color: "#78a9ff", weight: 1, fillOpacity: 0.1 });
  page.map.on("click", clickMap);
  for (const [slug, city] of Object.entries(page.cities)) {
    page.form.city.append(el("option", { value: slug, textContent: city.name }));
  }
  page.form.city.value = "la";
  page.form.city.addEventListener("change", pickCity);
  page.form.addEventListener("submit", countStreet);
  page.form.street.addEventListener("input", suggestStreets);
  page.form.street.addEventListener("change", suggestHouses);
  page.nearButton.addEventListener("click", useLocation);
  pickCity();
}

if (globalThis.document) start();
