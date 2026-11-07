"""NHL games on Disney+ in Finland, derived from the NHL's own schedule API.

Disney+ (Finland, Sweden) carries ESPN's NHL package, so the games are those the NHL lists
with a US national ESPN, ABC, ESPN+, Hulu or Disney+ broadcast. Finland's Disney+ games are not
published anywhere machine-readable, so this is an inference: check the Disney+ app if one is missing.

Endpoint: https://api-web.nhle.com/v1/schedule/YYYY-MM-DD (one week per request)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .http import get_json

API = "https://api-web.nhle.com/v1/schedule/"
DISNEY_URL = "https://www.disneyplus.com/"
NETWORKS = {"ESPN", "ESPN2", "ABC", "ESPN+", "HULU", "DISNEY+"}
GAME_LENGTH = timedelta(hours=3, minutes=15)


def _name(team: dict) -> str:
    return f'{(team.get("placeName") or {}).get("default", "")} {(team.get("commonName") or {}).get("default", "")}'.strip()


def parse(raw: dict) -> list[dict]:
    if not isinstance(raw, dict) or not isinstance(raw.get("gameWeek"), list):
        raise ValueError("NHL:n aikataulun rakenne muuttui")
    out = []
    for week_day in raw["gameWeek"]:
        for g in week_day.get("games") or []:
            if g.get("gameType") not in (2, 3):  # regular season, playoffs
                continue
            nets = {str(b.get("network", "")).strip().upper() for b in g.get("tvBroadcasts") or []
                    if b.get("countryCode") == "US"}
            if not nets & NETWORKS:
                continue
            try:
                start = datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00")).astimezone(timezone.utc)
            except (KeyError, ValueError):
                continue
            out.append({
                "sport": "nhl", "series": "NHL", "title": f'{_name(g["awayTeam"])} - {_name(g["homeTeam"])}',
                "session": "Runkosarja" if g.get("gameType") == 2 else "Pudotuspelit",
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": (start + GAME_LENGTH).isoformat().replace("+00:00", "Z"),
                "service": "Disney+", "channel": None, "free": False, "language": "en", "url": DISNEY_URL,
            })
    return out


def fetch(*, first_date: date, days: int) -> list[dict]:
    out, seen = [], set()
    for i in range(0, days + 1, 7):
        for item in parse(get_json(API + (first_date + timedelta(days=i)).isoformat())):
            key = (item["start"], item["title"])
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out
