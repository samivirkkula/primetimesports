"use strict";

const TZ = "Europe/Helsinki";
const STORE = "urheilu-tv:v1";
const SOURCE_NAMES = {
  "viaplay-f1": "Viaplay F1", "viaplay-motogp": "Viaplay MotoGP", "viaplay-moto2": "Viaplay Moto2",
  "viaplay-moto3": "Viaplay Moto3", "viaplay-nhl": "Viaplay NHL", "viaplay-darts": "Viaplay darts",
  "liiga": "Liigan otteluohjelma", "mtv": "MTV:n ohjelmaopas",
  "ruutu-nfl": "Ruudun NFL-ohjelma", "elisa": "Elisa Viihteen ohjelmaopas",
};

const $ = (id) => document.getElementById(id);
const fmtTime = new Intl.DateTimeFormat("fi-FI", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const fmtDayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const fmtWeekday = new Intl.DateTimeFormat("fi-FI", { timeZone: TZ, weekday: "long" });
const fmtDate = new Intl.DateTimeFormat("fi-FI", { timeZone: TZ, day: "numeric", month: "numeric" });
const fmtStamp = new Intl.DateTimeFormat("fi-FI", { timeZone: TZ, weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });

let data = null;
let fetchedAt = 0;
let state = { hidden: [], freeOnly: false, primeOnly: true };

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
  return ev.broadcasts.filter((b) => {
    if (state.freeOnly && !b.free) return false;
    return true;
  });
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

function renderList() {
  const list = $("list");
  const tpl = $("row");
  const now = Date.now();
  const todayKey = fmtDayKey.format(new Date(now));
  const tomorrowKey = fmtDayKey.format(new Date(now + 86400000));
  list.textContent = "";
  let lastKey = null;
  let shown = 0;

  for (const ev of data.events) {
    if (state.hidden.includes(ev.sport)) continue;
    const start = Date.parse(ev.start), end = Date.parse(ev.end);
    if (end <= now) continue;
    if (state.primeOnly && !isPrimetime(start)) continue;
    const bcs = visibleBroadcasts(ev);
    if (!bcs.length) continue;

    const key = fmtDayKey.format(new Date(start));
    if (key !== lastKey) {
      const h = document.createElement("h2");
      h.className = "day";
      const [name, date] = dayLabel(key, todayKey, tomorrowKey, start);
      h.append(name);
      const s = document.createElement("small");
      s.textContent = date;
      h.append(s);
      list.append(h);
      lastKey = key;
    }

    const row = tpl.content.firstElementChild.cloneNode(true);
    row.style.setProperty("--c", `var(--c-${ev.sport})`);
    const primary = bcs.find((b) => b.free) || bcs[0];
    row.href = primary.url || "#";
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
    row.setAttribute("aria-label",
      `${time(ev.start)} ${ev.series || ""} ${ev.title} ${ev.session || ""}, ${bcs.map((b) => b.service).join(", ")}`);
    list.append(row);
    shown++;
  }

  if (!shown) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = state.hidden.length === Object.keys(data.sports).length
      ? "Valitse ylhäältä ainakin yksi laji."
      : "Seuraavan kahden viikon aikana ei ole lähetyksiä näillä valinnoilla.";
    list.append(p);
  }
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
  add("Lähetystiedot: Viaplay, Liiga, MTV, Ruutu ja Elisa Viihde. Kaikki ajat Suomen aikaa.");
}

function render() {
  if (!data) return;
  $("updated").textContent = "Päivitetty\n" + fmtStamp.format(new Date(data.generated));
  renderChips();
  renderList();
  renderFoot();
}

async function load() {
  try {
    const res = await fetch("schedule.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
    fetchedAt = Date.now();
    render();
  } catch (err) {
    if (data) return; // keep showing what we have
    $("updated").textContent = "";
    const list = $("list");
    list.textContent = "";
    const p = document.createElement("p");
    p.className = "error";
    p.textContent = "Aikataulua ei voitu ladata. Tarkista verkkoyhteys ja avaa sovellus uudelleen.";
    list.append(p);
  }
}

loadState();
$("primeOnly").checked = state.primeOnly;
$("primeOnly").addEventListener("change", (e) => { state.primeOnly = e.target.checked; saveState(); renderList(); });
$("freeOnly").checked = state.freeOnly;
$("freeOnly").addEventListener("change", (e) => { state.freeOnly = e.target.checked; saveState(); renderList(); });

load();
setInterval(() => data && renderList(), 60_000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && Date.now() - fetchedAt > 15 * 60_000) load();
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
