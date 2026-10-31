"""World Rally Championship stage times from WRC's public results API.

Calendar:  https://api.wrc.com/contel-page/83388/calendar/active-season/
           -> rallyEvents.items[] (id, name, eventDays ...)
Itinerary: https://api.wrc.com/results-api/rally-event/<id>/itinerary
           -> itineraryLegs[].itinerarySections[] with stages[] (stageId, code "SS5", name,
              distance) and controls[] (type "StageStart", stageId, firstCarDueDateTimeLocal)

All stages stream live on MTV Katsomo+ Urheilu in Finland. Field names follow the public
API as documented by rallydatajunkie.com; the parser is tolerant of extra/missing fields.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from .http import get_json

CALENDAR = "https://api.wrc.com/contel-page/83388/calendar/active-season/"
ITINERARY = "https://api.wrc.com/results-api/rally-event/{id}/itinerary"
KATSOMO = "https://www.mtv.fi/urheilu/ralli"
STAGE_LENGTH = timedelta(minutes=75)  # first to last car on a typical stage
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})")


def _dates(node, out: set[date]) -> set[date]:
    if isinstance(node, str):
        for m in _DATE.findall(node):
            try:
                out.add(date.fromisoformat(m))
            except ValueError:
                pass
    elif isinstance(node, dict):
        for v in node.values():
            _dates(v, out)
    elif isinstance(node, list):
        for v in node:
            _dates(v, out)
    return out


def rally_name(name: str) -> str:
    """'WRC Rally Saudi Arabia' -> 'Rally Saudi Arabia'."""
    return re.sub(r"^\s*(FIA\s+)?WRC\s+", "", name or "").strip() or "MM-ralli"


def events_in_window(raw: dict, first: date, last: date) -> list[dict]:
    items = ((raw or {}).get("rallyEvents") or {}).get("items")
    if not isinstance(items, list):
        raise ValueError("WRC:n kalenterin rakenne muuttui (rallyEvents.items puuttuu)")
    out = []
    for it in items:
        if not isinstance(it, dict) or it.get("deleted") or it.get("id") is None:
            continue
        ds = _dates(it.get("eventDays") or it, set())
        if not ds:
            continue
        if min(ds) <= last and max(ds) >= first - timedelta(days=1):
            out.append({"id": it["id"], "name": rally_name(it.get("name", ""))})
    return out


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_itinerary(raw: dict, *, rally: str, event_id) -> list[dict]:
    legs = (raw or {}).get("itineraryLegs")
    if not isinstance(legs, list):
        raise ValueError("WRC:n aikataulun rakenne muuttui (itineraryLegs puuttuu)")
    events = []
    for leg in legs:
        for sec in leg.get("itinerarySections") or []:
            starts = {}
            for c in sec.get("controls") or []:
                if c.get("type") == "StageStart" and c.get("stageId") is not None:
                    dt = _parse_dt(c.get("firstCarDueDateTimeLocal")) or _parse_dt(c.get("firstCarDueDateTime"))
                    if dt:
                        starts[c["stageId"]] = dt.astimezone(timezone.utc)
            for st in sec.get("stages") or []:
                start = starts.get(st.get("stageId"))
                if not start:
                    continue
                code = re.sub(r"^SS", "EK", str(st.get("code") or "").strip())
                name = re.sub(r"\s*\(live tv\)\s*", " ", str(st.get("name") or ""), flags=re.I).strip()
                dist = st.get("distance")
                session = f"{code} {name}".strip()
                if isinstance(dist, (int, float)) and dist > 0:
                    session += f" ({str(round(dist, 1)).replace('.', ',')} km)"
                events.append({
                    "sport": "wrc", "series": "MM-ralli", "title": rally, "session": session,
                    "start": start.isoformat().replace("+00:00", "Z"),
                    "end": (start + STAGE_LENGTH).isoformat().replace("+00:00", "Z"),
                    "service": "MTV Katsomo+", "channel": None, "free": False, "language": "fi",
                    "url": KATSOMO, "source_id": f"wrc-{event_id}-{st.get('stageId')}",
                })
    return events


def fetch(*, first: date, last: date) -> list[dict]:
    rallies = events_in_window(get_json(CALENDAR), first, last)
    out = []
    for r in rallies:
        out += parse_itinerary(get_json(ITINERARY.format(id=r["id"])), rally=r["name"], event_id=r["id"])
    return out
