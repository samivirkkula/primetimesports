"""Fetch all sources, merge broadcasts per event and write site/schedule.json.

Run:  python -m scraper.build            (fetch from the network)
      python -m scraper.build --cached   (rebuild from .cache only)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import elisa, liiga, mtv, ruutu, viaplay

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
OUT = ROOT / "site"
MAX_CACHE_AGE = timedelta(hours=72)
STOP = {"nhl", "liiga", "live", "suora", "lähetys", "ottelu", "jääkiekko", "runkosarja"}


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zåäö0-9]{3,}", text.lower()) if t not in STOP}


# ---------------------------------------------------------------- sources
def run_source(name: str, fn, now: datetime, offline: bool, status: dict) -> list[dict]:
    path = CACHE / f"{name}.json"
    if not offline:
        try:
            items = fn()
            CACHE.mkdir(exist_ok=True)
            path.write_text(json.dumps({"fetched": now.isoformat(), "items": items}, ensure_ascii=False))
            status[name] = {"state": "ok", "count": len(items), "fetched": now.isoformat()}
            return items
        except Exception as exc:  # keep going with other sources
            traceback.print_exc()
            status[name] = {"state": "error", "error": str(exc)[:300]}
    if path.exists():
        cached = json.loads(path.read_text())
        age = now - datetime.fromisoformat(cached["fetched"])
        if age <= MAX_CACHE_AGE or offline:
            status.setdefault(name, {})
            status[name].update(state=status[name].get("state", "cached") if not offline else "cached",
                                cached_from=cached["fetched"], count=len(cached["items"]))
            return cached["items"]
        status[name]["stale"] = True
    return []


# ---------------------------------------------------------------- merging
def to_event(e: dict) -> dict:
    keys = ("service", "channel", "free", "language", "url")
    return {
        "sport": e["sport"], "series": e.get("series"), "title": e["title"],
        "session": e.get("session", ""), "start": e["start"], "end": e.get("end"),
        "teams": e.get("teams"),
        "broadcasts": [{k: e.get(k) for k in keys} | {"manual": e.get("manual", False)}],
    }


def find_match(events: list[dict], sport: str, start: datetime, title: str,
               before=timedelta(minutes=75), after=timedelta(minutes=30)) -> dict | None:
    """Same sport, broadcast start close to event start, overlapping title words.
    Returns a match only if it is unambiguous."""
    words = tokens(title)
    hits = []
    for ev in events:
        if ev["sport"] != sport:
            continue
        delta = start - parse_ts(ev["start"])
        if not (-before <= delta <= after):
            continue
        ev_words = tokens(" ".join(ev.get("teams") or []) or ev["title"])
        if words & ev_words:
            hits.append(ev)
    return hits[0] if len(hits) == 1 else None


def add_broadcast(ev: dict, b: dict) -> None:
    for old in ev["broadcasts"]:
        if old["service"] == b["service"] and old.get("channel") == b.get("channel"):
            return
    ev["broadcasts"].append(b)


def merge(viaplay_items, liiga_items, mtv_items, overrides,
          nfl_items=(), free_nfl=()) -> tuple[list[dict], dict]:
    report = {"mtv_unmatched": [], "nfl_free_unmatched": []}
    events = [to_event(e) for e in liiga_items] + [to_event(e) for e in nfl_items]

    # Viaplay: one product per broadcast; NHL games can also be on MTV Sub/Disney+.
    for e in viaplay_items:
        events.append(to_event(e))

    for item in mtv_items:
        start = parse_ts(item["start"])
        b = {"service": item["channel"], "channel": item["channel"], "free": True,
             "language": "fi", "url": mtv.GUIDE, "manual": False}
        if re.search(r"\bNHL\b", item["title"], re.I):
            ev = find_match(events, "nhl", start, item["title"])
            if ev:
                add_broadcast(ev, b)
            else:
                events.append({"sport": "nhl", "series": "NHL", "title": re.sub(r"^\s*NHL\s*[:\-–]?\s*", "", item["title"]),
                               "session": "", "start": item["start"], "end": item.get("end"),
                               "teams": None, "broadcasts": [b]})
            continue
        ev = find_match(events, "liiga", start, item["title"])
        if ev:
            add_broadcast(ev, b)
        elif re.search(r"liiga", item["title"], re.I):
            report["mtv_unmatched"].append(item)

    # Free-to-air NFL (e.g. Jim simulcasting Ruutu's Finnish-commentary game). The guide
    # title may not name the teams, so the slot itself is the match: a single Finnish
    # Ruutu game starting within 20 minutes.
    for item in free_nfl:
        start = parse_ts(item["start"])
        b = {"service": item["channel"], "channel": item["channel"], "free": True,
             "language": "fi", "url": elisa.GUIDE, "manual": False}
        ev = find_match(events, "nfl", start, f'{item["title"]} {item["description"]}',
                        before=timedelta(minutes=20), after=timedelta(minutes=20))
        if not ev:
            slot = [e for e in events if e["sport"] == "nfl"
                    and abs(start - parse_ts(e["start"])) <= timedelta(minutes=20)
                    and any(x.get("language") == "fi" for x in e["broadcasts"])]
            ev = slot[0] if len(slot) == 1 else None
        if ev:
            add_broadcast(ev, b)
        else:
            report["nfl_free_unmatched"].append(item)

    for o in overrides:
        o = dict(o, manual=True)
        ev = find_match(events, o["sport"], parse_ts(o["start"]), o["title"])
        if ev:
            add_broadcast(ev, to_event(o)["broadcasts"][0])
        else:
            events.append(to_event(o))
    return events, report


def in_window(start: datetime, window, tz) -> bool:
    """True if the local start time is within [from, to] (inclusive), e.g. ["16:00", "23:00"]."""
    if not window:
        return True
    hm = start.astimezone(tz).strftime("%H:%M")
    lo, hi = window
    return lo <= hm <= hi if lo <= hi else (hm >= lo or hm <= hi)  # also handles windows over midnight


def finalize(events: list[dict], now: datetime, last: datetime,
             windows: dict | None = None, tz=None) -> list[dict]:
    out = []
    for ev in events:
        start = parse_ts(ev["start"])
        end = parse_ts(ev["end"]) if ev.get("end") else start + timedelta(hours=2)
        if end < now or start > last:
            continue
        if windows and not in_window(start, windows.get(ev["sport"]), tz):
            continue
        ev["end"] = end.isoformat().replace("+00:00", "Z")
        ev["id"] = hashlib.sha1(f'{ev["sport"]}|{ev["title"]}|{ev["session"]}|{ev["start"]}'.encode()).hexdigest()[:12]
        ev.pop("teams", None)
        out.append(ev)
    # de-duplicate identical products that appear on several Viaplay pages
    uniq = {}
    for ev in out:
        if ev["id"] in uniq:
            for b in ev["broadcasts"]:
                add_broadcast(uniq[ev["id"]], b)
        else:
            uniq[ev["id"]] = ev
    return sorted(uniq.values(), key=lambda e: (e["start"], e["sport"], e["title"]))


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cached", action="store_true", help="älä hae verkosta, käytä välimuistia")
    ap.add_argument("--now", help="ISO-aikaleima toistettavaa ajoa varten")
    args = ap.parse_args(argv)

    cfg = json.loads((ROOT / "config.json").read_text())
    tz = ZoneInfo(cfg["timezone"])
    now = parse_ts(args.now) if args.now else datetime.now(timezone.utc)
    local_today = now.astimezone(tz).date()
    days = int(cfg["days"])
    last = datetime.combine(local_today + timedelta(days=days), datetime.min.time(), tz).astimezone(timezone.utc)
    first_date, last_date = local_today.isoformat(), (local_today + timedelta(days=days - 1)).isoformat()
    enabled = {k for k, v in cfg["sports"].items() if v.get("enabled")}
    extra = set(cfg.get("motorsport_extra_feeds", []))
    status: dict = {}

    viaplay_items = []
    for sport, vcfg in cfg["viaplay"].items():
        if sport in enabled:
            viaplay_items += run_source(
                f"viaplay-{sport}",
                lambda s=sport, c=vcfg: viaplay.fetch(s, c, first_date=first_date, last_date=last_date, extra_feeds=extra),
                now, args.cached, status)
    liiga_items = run_source("liiga", lambda: liiga.fetch(first=now - timedelta(hours=3), last=last),
                             now, args.cached, status) if "liiga" in enabled else []
    mtv_items = run_source("mtv", lambda: mtv.fetch(first_date=local_today, days=days),
                           now, args.cached, status) if enabled & {"liiga", "nhl"} else []
    nfl_items = run_source("ruutu-nfl", lambda: ruutu.fetch(today=local_today),
                           now, args.cached, status) if "nfl" in enabled else []
    free_nfl = run_source("elisa", lambda: elisa.fetch(first_date=local_today, days=days),
                          now, args.cached, status) if "nfl" in enabled else []

    overrides_path = ROOT / "data" / "overrides.json"
    overrides = [o for o in json.loads(overrides_path.read_text()) if not o.get("_example")] if overrides_path.exists() else []

    events, report = merge(viaplay_items, liiga_items, mtv_items, overrides, nfl_items, free_nfl)
    windows = {k: v.get("start_window") for k, v in cfg["sports"].items() if v.get("start_window")}
    events = finalize(events, now, last, windows, tz)

    nhl_lang = {}
    for e in viaplay_items:
        if e["sport"] == "nhl":
            nhl_lang[str(e.get("language"))] = nhl_lang.get(str(e.get("language")), 0) + 1
    status["nhl_viaplay_languages"] = nhl_lang

    OUT.mkdir(exist_ok=True)
    payload = {
        "generated": now.isoformat().replace("+00:00", "Z"),
        "timezone": cfg["timezone"],
        "sports": {k: v["name"] for k, v in cfg["sports"].items() if k in enabled},
        "events": events,
        "status": status,
    }
    (OUT / "schedule.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    CACHE.mkdir(exist_ok=True)
    (CACHE / "match-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))

    print(f"{len(events)} tapahtumaa -> {OUT / 'schedule.json'}")
    for name, st in status.items():
        print(f"  {name}: {st}")
    fetched_any = any(isinstance(s, dict) and s.get("state") in ("ok", "cached") and s.get("count") for s in status.values())
    if not events and not fetched_any:
        print("Yksikään lähde ei tuottanut dataa – julkaisu ohitetaan.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
