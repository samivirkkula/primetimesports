"""Liiga's public schedule API. All games stream on MTV Katsomo+ with Finnish commentary."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .http import get_json

API = "https://liiga.fi/api/v2/schedule?tournament={tournament}&week=1&season={season}"
KATSOMO = "https://www.mtv.fi/urheilu/jaakiekko/liiga"


def season_for(d: date) -> int:
    # The 2026-27 season is "2027" in the API; it starts in September.
    return d.year + 1 if d.month >= 9 else d.year


def parse(raw: list, *, first: datetime, last: datetime, tournament: str) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("Liigan otteluohjelman rakenne muuttui (odotettiin listaa)")
    events = []
    for g in raw:
        start_s, home, away = g.get("start"), g.get("homeTeamName"), g.get("awayTeamName")
        if not start_s or not home or not away:
            continue  # unresolved playoff pairs
        start = datetime.fromisoformat(start_s.replace("Z", "+00:00")).astimezone(timezone.utc)
        if not (first <= start <= last) or g.get("ended"):
            continue
        events.append({
            "sport": "liiga",
            "series": "Liiga" if tournament == "runkosarja" else "Liiga, pudotuspelit",
            "title": f"{home} – {away}",
            "session": "",
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": (start + timedelta(hours=2, minutes=40)).isoformat().replace("+00:00", "Z"),
            "service": "MTV Katsomo+",
            "channel": None,
            "free": False,
            "language": "fi",
            "url": KATSOMO,
            "source_id": f"liiga-{g.get('season')}-{g.get('id')}",
            "teams": [home, away],
        })
    return events


def fetch(*, first: datetime, last: datetime) -> list[dict]:
    seasons = sorted({season_for(first.date()), season_for(last.date())})
    events = []
    for season in seasons:
        for tournament in ("runkosarja", "playoffs"):
            try:
                raw = get_json(API.format(tournament=tournament, season=season))
            except RuntimeError:
                if tournament == "playoffs":
                    continue  # not published until spring
                raise
            events += parse(raw, first=first, last=last, tournament=tournament)
    return events
