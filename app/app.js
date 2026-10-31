"use strict";

const TZ = "Europe/Helsinki";
const STORE = "urheilu-tv:v1";
const SOURCE_NAMES = {
  "viaplay-f1": "Viaplay F1", "viaplay-motogp": "Viaplay MotoGP", "viaplay-moto2": "Viaplay Moto2",
  "viaplay-moto3": "Viaplay Moto3", "viaplay-nhl": "Viaplay NHL", "viaplay-darts": "Viaplay darts",
  "liiga": "Liigan otteluohjelma", "mtv": "MTV:n ohjelmaopas",
  "ruutu-nfl": "Ruudun NFL-ohjelma", "elisa": "Elisa Viihteen ohjelmaopas", "wrc": "WRC:n aikataulu",
};

const $ = (id) => document.getElementById(id);
const fmtTime = new Intl.DateTimeFormat("fi-FI", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const fmtDayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const fmtWeekday = new Intl.DateTimeFormat("fi-FI", { timeZone: TZ, weekday: "long" });
const fmtDate = new Intl.DateTimeFormat("fi-FI", { timeZone: TZ, day: "numeric", month: "numeric" });
const fmtStamp = new Intl.DateTimeFormat("fi-FI", { timeZone: TZ, weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });

let data = null;
let fetchedAt = 0;
let state = { hidden: [], primeOnly: true };

// Primetime: broadcasts starting 15.00–23.00 Finnish time (both ends inclusive).
const PRIME_FROM = "15:00", PRIME_TO = "23:00";
const fmtHM = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const isPrimetime = (ms) => { const hm = fmtHM.format(new Date(ms)); return hm >= PRIME_FROM && hm <= PRIME_TO; };

function loadState() {
  try {
    const s = JSON.parse(localStorage.getItem(STORE));
    if (s && typeof s === "object") state = { ...state, ...s };
  } catch { /* storage unavailable: defaults */ }
}
function saveState() {
  try { localStorage.setItem(STORE, JSON.stringify(state)); } catch { /* ignore */ }
}

const time = (iso) => fmtTime.format(new Date(iso)).replace(":", ".");

function dayLabel(key, todayKey, tomorrowKey, sample) {
  const d = new Date(sample);
  const date = fmtDate.format(d);
  if (key === todayKey) return ["Tänään", date];
  if (key === tomorrowKey) return ["Huomenna", date];
  const wd = fmtWeekday.format(d);
  return [wd.charAt(0).toUpperCase() + wd.slice(1), date];
}

function visibleBroadcasts(ev) {
  return ev.broadcasts || [];
}

function renderChips() {
  const chips = $("chips");
  chips.textContent = "";
  for (const [key, name] of Object.entries(data.sports)) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = name;
    b.style.setProperty("--c", `var(--c-${key})`);
    b.setAttribute("aria-pressed", String(!state.hidden.includes(key)));
    b.addEventListener("click", () => {
      state.hidden = state.hidden.includes(key) ? state.hidden.filter((k) => k !== key) : [...state.hidden, key];
      saveState();
      renderChips();
      renderList();
    });
    chips.append(b);
  }
}

// Day accordion: today is open, other days are stacked closed. Scrolling down opens
// the next day when its header reaches the lower part of the screen; scrolling back up
// closes those auto-opened days again. A tap opens or closes a day for good.
// State lives in memory so the minute refresh keeps it.
// dayKey -> "auto" (opened by scrolling) | "stack" (closed, scrolling may open it)
//         | "open" | "closed" (set by the user; scrolling leaves these alone)
const dayState = new Map();
const OPEN_LINE = 0.8, CLOSE_LINE = 0.86; // fractions of the viewport height; the gap prevents flicker

function dayBlock(day, open) {
  const sec = document.createElement("section");
  sec.className = "dayblock" + (open ? " open" : "");
  sec.dataset.key = day.key;
  const h = document.createElement("h2");
  h.className = "dayhead";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "day";
  btn.id = `h-${day.key}`;
  btn.setAttribute("aria-expanded", String(open));
  btn.setAttribute("aria-controls", `d-${day.key}`);
  const name = document.createElement("span");
  name.className = "dname";
  name.textContent = day.name;
  const date = document.createElement("small");
  date.textContent = day.date;
  const sum = document.createElement("span");
  sum.className = "dsum";
  for (const sport of day.sports) {
    const dot = document.createElement("i");
    dot.style.setProperty("--c", `var(--c-${sport})`);
    sum.append(dot);
  }
  sum.append(day.rows.length === 1 ? "1 lähetys" : `${day.rows.length} lähetystä`);
  const chev = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  chev.setAttribute("viewBox", "0 0 24 24");
  chev.setAttribute("aria-hidden", "true");
  chev.classList.add("chev");
  chev.innerHTML = '<path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
  btn.append(name, date, sum, chev);
  btn.addEventListener("click", () => setDay(sec, !sec.classList.contains("open"), "user"));
  h.append(btn);
  const body = document.createElement("div");
  body.className = "daybody";
  body.id = `d-${day.key}`;
  body.setAttribute("role", "region");
  body.setAttribute("aria-labelledby", btn.id);
  if (!open) body.inert = true;
  const inner = document.createElement("div");
  inner.className = "dayinner";
  inner.append(...day.rows);
  body.append(inner);
  sec.append(h, body);
  return sec;
}

function setDay(sec, open, how) {
  sec.classList.toggle("open", open);
  sec.querySelector(".day").setAttribute("aria-expanded", String(open));
  sec.querySelector(".daybody").inert = !open;
  const key = sec.dataset.key;
  if (how === "user") dayState.set(key, open ? "open" : "closed");
  else if (open) dayState.set(key, "auto");
  else dayState.set(key, "stack"); // closed by scrolling or "collapse all": may open again on the way down
  updateClosedPadding();
}

function collapseAll() {
  for (const sec of document.querySelectorAll(".dayblock")) setDay(sec, false, "auto");
  lastScrollY = window.scrollY;
}

function updateClosedPadding() {
  // While closed days remain, leave room below so scrolling can always reach and open them.
  const list = $("list");
  list.classList.toggle("has-closed", Boolean(list.querySelector(".dayblock:not(.open)")));
}

let lastScrollY = 0;
function onScroll() {
  const y = window.scrollY;
  const maxY = document.documentElement.scrollHeight - window.innerHeight;
  if (y < 0 || y > maxY) return; // iOS rubber-band bounce
  if (y <= 2) {
    // Back at the top: return to the starting view.
    for (const sec of document.querySelectorAll(".dayblock.open")) {
      if (dayState.get(sec.dataset.key) === "auto") setDay(sec, false, "auto");
    }
    lastScrollY = y;
    return;
  }
  const delta = y - lastScrollY;
  if (Math.abs(delta) < 4) return;
  lastScrollY = y;
  const vh = window.innerHeight;
  const blocks = [...document.querySelectorAll(".dayblock")];
  if (delta > 0) {
    for (const sec of blocks) {
      if (sec.classList.contains("open") || dayState.get(sec.dataset.key) === "closed") continue;
      if (sec.getBoundingClientRect().top < vh * OPEN_LINE) setDay(sec, true, "auto");
      break; // one day per scroll step; opening pushes the next ones down
    }
  } else {
    // Bottom-most first: a day below the reading position closes without moving what is on screen.
    for (const sec of blocks.reverse()) {
      if (dayState.get(sec.dataset.key) !== "auto") continue;
      if (sec.getBoundingClientRect().top > vh * CLOSE_LINE) setDay(sec, false, "auto");
      break;
    }
  }
}

function renderList() {
  const list = $("list");
  const tpl = $("row");
  const now = Date.now();
  const todayKey = fmtDayKey.format(new Date(now));
  const tomorrowKey = fmtDayKey.format(new Date(now + 86400000));
  const days = [];

  for (const ev of data.events) {
    if (state.hidden.includes(ev.sport)) continue;
    const start = Date.parse(ev.start), end = Date.parse(ev.end);
    if (end <= now) continue;
    if (state.primeOnly && !isPrimetime(start)) continue;
    const bcs = visibleBroadcasts(ev);
    if (!bcs.length) continue;

    const key = fmtDayKey.format(new Date(start));
    let day = days[days.length - 1];
    if (!day || day.key !== key) {
      const [name, date] = dayLabel(key, todayKey, tomorrowKey, start);
      day = { key, name, date, rows: [], sports: new Set() };
      days.push(day);
    }
    day.sports.add(ev.sport);

    const row = tpl.content.firstElementChild.cloneNode(true);
    row.style.setProperty("--c", `var(--c-${ev.sport})`);
    const primary = bcs.find((b) => b.free) || bcs[0];
    const go = row.querySelector(".go");
    go.href = primary.url || "#";
    const remind = row.querySelector(".remind");
    remind.href = `ics/${ev.id}.ics`;
    remind.setAttribute("aria-label", `Muistuta: lisää kalenteriin ${ev.title}, hälytys 15 min ennen`);
    if (start <= now) row.classList.add("now");
    const t = row.querySelector(".t");
    t.textContent = time(ev.start);
    t.dateTime = ev.start;
    row.querySelector(".series").textContent = ev.series || data.sports[ev.sport] || "";
    row.querySelector(".title").textContent = ev.title;
    row.querySelector(".session").textContent = ev.session || "";
    const where = row.querySelector(".where");
    for (const b of bcs) {
      const span = document.createElement("span");
      span.className = "svc" + (b.free ? " free" : "") + (b.manual ? " manual" : "");
      span.textContent = b.service;
      where.append(span);
    }
    go.setAttribute("aria-label",
      `${time(ev.start)} ${ev.series || ""} ${ev.title} ${ev.session || ""}, ${bcs.map((b) => b.service).join(", ")}`);
    day.rows.push(row);
  }

  list.textContent = "";
  if (!days.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = state.hidden.length === Object.keys(data.sports).length
      ? "Valitse ylhäältä ainakin yksi laji."
      : "Seuraavan kahden viikon aikana ei ole lähetyksiä näillä valinnoilla.";
    list.append(p);
    updateClosedPadding();
    return;
  }
  const defaultOpen = days.some((d) => d.key === todayKey) ? todayKey : days[0].key;
  for (const day of days) {
    const saved = dayState.get(day.key);
    const open = saved ? saved === "open" || saved === "auto" : day.key === defaultOpen;
    list.append(dayBlock(day, open));
  }
  updateClosedPadding();
}

function renderFoot() {
  const foot = $("foot");
  foot.textContent = "";
  const add = (text) => { const p = document.createElement("p"); p.textContent = text; foot.append(p); };
  for (const [name, st] of Object.entries(data.status || {})) {
    if (!SOURCE_NAMES[name] || !st || st.state !== "error") continue;
    add(st.cached_from
      ? `${SOURCE_NAMES[name]}: haku epäonnistui, näytetään ${fmtStamp.format(new Date(st.cached_from))} haetut tiedot.`
      : `${SOURCE_NAMES[name]}: haku epäonnistui, tämän lähteen lähetykset puuttuvat.`);
  }
  if (data.events.some((e) => e.broadcasts.some((b) => b.manual))) add("* Käsin lisätty lähetys.");
  add("Lähetystiedot: Viaplay, Liiga, MTV, Ruutu, Elisa Viihde ja WRC. Kaikki ajat Suomen aikaa.");
}

function render() {
  if (!data) return;
  $("updated").textContent = "Päivitetty\n" + fmtStamp.format(new Date(data.generated));
  renderChips();
  renderList();
  renderFoot();
}

function showError(text) {
  const upd = $("updated");
  if (upd) upd.textContent = "";
  const list = $("list");
  if (!list) return;
  list.textContent = "";
  const p = document.createElement("p");
  p.className = "error";
  p.textContent = text;
  list.append(p);
}

async function load() {
  let fresh;
  try {
    const res = await fetch("schedule.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    fresh = await res.json();
  } catch (err) {
    if (!data) showError("Aikataulua ei voitu ladata. Tarkista verkkoyhteys ja avaa sovellus uudelleen.");
    return;
  }
  data = fresh;
  fetchedAt = Date.now();
  try {
    render();
  } catch (err) {
    showError(`Aikataulun näyttäminen epäonnistui: ${err && err.message ? err.message : err}`);
  }
}

// Bind a checkbox if it exists. An older cached index.html may lack a newer toggle;
// the app must still start.
function bindToggle(id, key) {
  const el = $(id);
  if (!el) return;
  el.checked = Boolean(state[key]);
  el.addEventListener("change", (e) => { state[key] = e.target.checked; saveState(); if (data) renderList(); });
}

window.addEventListener("error", (e) => {
  if (!data) showError(`Sovellus kaatui: ${e.message}. Sulje sovellus kokonaan ja avaa uudelleen.`);
});

loadState();
bindToggle("primeOnly", "primeOnly");
const collapseBtn = $("collapseAll");
if (collapseBtn) collapseBtn.addEventListener("click", collapseAll);

load();
window.addEventListener("scroll", onScroll, { passive: true });
setInterval(() => data && renderList(), 60_000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && Date.now() - fetchedAt > 15 * 60_000) load();
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
