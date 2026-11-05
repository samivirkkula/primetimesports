"""Elisa Viihde's public TV guide API: live NFL games on free-to-air channels (Jim, Nelonen, Hero).

Endpoints: https://viihde-epg-api-prod.csf.elisa.fi/epg/channels
           https://viihde-epg-api-prod.csf.elisa.fi/epg/schedule?channelId=..&timeRange=FROM,TO
At most seven calendar days per schedule request.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from .http import get_json

API = "https://viihde-epg-api-prod.csf.elisa.fi/epg"
GUIDE = "https://elisaviihde.fi/ohjelmaopas"
CHANNELS = ("Jim", "Nelonen", "Hero")
NATIONAL_CHANNEL = "TV5"


def _iso_ms(ms) -> str | None:
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def parse(raw: dict) -> list[dict]:
    if not isinstance(raw, dict) or not isinstance(raw.get("schedule"), list):
        raise ValueError("Elisan ohjelmaoppaan rakenne muuttui")
    out = []
    for day in raw["schedule"]:
        for p in day.get("programs") or []:
            channel = (p.get("channel") or {}).get("name")
            if channel not in CHANNELS:
                continue
            name, desc = p.get("name") or "", p.get("shortDescription") or ""
            text = f"{name} {desc}"
            if not re.search(r"\bNFL\b", text) or re.search(r"uusinta|replay|kooste|highlights|redzone", text, re.I):
                continue
            if not re.search(r"suora|live", text, re.I):
                continue
            start = _iso_ms(p.get("startTimeUTC"))
            if not start:
                continue
            out.append({"title": name.strip(), "description": desc.strip(), "start": start,
                        "end": _iso_ms(p.get("endTimeUTC")), "channel": channel, "id": p.get("id")})
    return out


def fetch(*, first_date: date, days: int) -> list[dict]:
    raw = get_json(f"{API}/channels")
    chans = [c for c in raw.get("channels", []) if c.get("name") in CHANNELS]
    if not chans:
        raise RuntimeError("Elisan kanavalistasta puuttuvat Jim, Nelonen ja Hero")
    out, seen = [], set()
    for c in chans:
        for i in range(0, days, 7):
            a = first_date + timedelta(days=i)
            b = first_date + timedelta(days=min(days - 1, i + 6))
            q = urlencode({"channelId": c["id"], "timeRange": f"{a}T00:00:01,{b}T23:59:59", "showHiddenChannels": "true"})
            for item in parse(get_json(f"{API}/schedule?{q}")):
                key = (item["channel"], item["id"], item["start"])
                if key not in seen:
                    seen.add(key)
                    out.append(item)
    return out


def parse_national(raw: dict) -> list[dict]:
    """Live Finland national-team games on TV5: "Jääkiekon Nocco Hockey Games: Sveitsi-Suomi", description "Suora lähetys ..."."""
    if not isinstance(raw, dict) or not isinstance(raw.get("schedule"), list):
        raise ValueError("Elisan ohjelmaoppaan rakenne muuttui")
    out = []
    for day in raw["schedule"]:
        for p in day.get("programs") or []:
            if (p.get("channel") or {}).get("name") != NATIONAL_CHANNEL:
                continue
            name, desc = (p.get("name") or "").strip(), (p.get("shortDescription") or "").strip()
            series, _, teams = name.rpartition(": ")
            if not series or not re.search(r"\bSuomi\b", teams) or not re.match(r"suora", desc, re.I):
                continue
            start = _iso_ms(p.get("startTimeUTC"))
            if not start:
                continue
            out.append({"sport": "maajoukkue", "series": re.sub(r"^Jääkiekon\s+", "", series),
                        "title": teams.replace("-", " – "), "session": "", "start": start,
                        "end": _iso_ms(p.get("endTimeUTC")), "service": NATIONAL_CHANNEL, "channel": NATIONAL_CHANNEL,
                        "free": True, "language": "fi", "url": GUIDE, "id": p.get("id")})
    return out


def fetch_national(*, first_date: date, days: int) -> list[dict]:
    raw = get_json(f"{API}/channels")
    chans = [c for c in raw.get("channels", []) if c.get("name") == NATIONAL_CHANNEL]
    if not chans:
        raise RuntimeError("Elisan kanavalistasta puuttuu TV5")
    out, seen = [], set()
    for i in range(0, days, 7):
        a = first_date + timedelta(days=i)
        b = first_date + timedelta(days=min(days - 1, i + 6))
        q = urlencode({"channelId": chans[0]["id"], "timeRange": f"{a}T00:00:01,{b}T23:59:59", "showHiddenChannels": "true"})
        for item in parse_national(get_json(f"{API}/schedule?{q}")):
            if (item["id"], item["start"]) not in seen:
                seen.add((item["id"], item["start"]))
                out.append(item)
    return out
