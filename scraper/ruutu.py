"""Ruutu's NFL page (https://www.ruutu.fi/ohjelmat/nfl): upcoming live game streams on Ruutu+ Urheilu.

The page lists each live stream as a link to /stream/<id> with a title, a time element
("<strong>20:00</strong>1.11.") and an image whose alt text tells the commentary
language ("Selostus suomi"). RedZone and recordings are skipped.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .http import request

URL = "https://www.ruutu.fi/ohjelmat/nfl"
TZ = ZoneInfo("Europe/Helsinki")
GAME = re.compile(r".+\s(?:-|–|—|vs\.?|@)\s.+", re.I)


class _Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1 = ""
        self.cards: list[dict] = []
        self._card: dict | None = None
        self._depth = 0          # nesting depth inside the current <a>
        self._mode: list[tuple[int, str]] = []  # (depth, kind) for title/time/strong/h1
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "h1":
            self._in_h1 = True
        if self._card is None:
            if tag == "a" and (a.get("href") or "").startswith("/stream/"):
                self._card = {"href": a["href"], "title": "", "clock": "", "time": "", "alts": []}
                self._depth = 1
            return
        if tag not in ("img", "br", "source", "meta", "input"):
            self._depth += 1
        if tag == "img" and a.get("alt"):
            self._card["alts"].append(a["alt"])
        if "titleText" in cls:
            self._mode.append((self._depth, "title"))
        elif "__time" in cls:
            self._mode.append((self._depth, "time"))
        elif tag == "strong" and any(k == "time" for _, k in self._mode):
            self._mode.append((self._depth, "clock"))

    def handle_endtag(self, tag):
        if tag == "h1":
            self._in_h1 = False
        if self._card is None:
            return
        while self._mode and self._mode[-1][0] >= self._depth:
            self._mode.pop()
        self._depth -= 1
        if self._depth == 0:
            self.cards.append(self._card)
            self._card = None
            self._mode.clear()

    def handle_data(self, data):
        if self._in_h1:
            self.h1 += data
        if self._card is None or not self._mode:
            return
        kinds = {k for _, k in self._mode}
        if "clock" in kinds:
            self._card["clock"] += data
        elif "time" in kinds:
            self._card["time"] += data
        elif "title" in kinds:
            self._card["title"] += data


def _event_date(day: int, month: int, today: date) -> date | None:
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if today - timedelta(days=1) <= d <= today + timedelta(days=40):
            return d
    return None


def parse(html: str, *, today: date) -> list[dict]:
    p = _Cards()
    p.feed(html)
    if "NFL" not in p.h1:
        raise ValueError("Ruudun NFL-sivun rakenne muuttui (otsikko puuttuu)")
    events = []
    for c in p.cards:
        title = " ".join(c["title"].split())
        clock = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", c["clock"])
        day = re.search(r"(\d{1,2})\.(\d{1,2})\.", c["time"])
        if not title or not clock or not day:
            continue
        if "redzone" in title.lower() or not GAME.match(title):
            continue
        d = _event_date(int(day.group(1)), int(day.group(2)), today)
        if not d:
            continue
        local = datetime(d.year, d.month, d.day, int(clock.group(1)), int(clock.group(2)), tzinfo=TZ)
        start = local.astimezone(timezone.utc)
        fi = any(re.search(r"selostus\s+suomi", alt, re.I) for alt in c["alts"])
        events.append({
            "sport": "nfl", "series": "NFL", "title": title.replace(" - ", " – "), "session": "",
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": (start + timedelta(hours=3, minutes=30)).isoformat().replace("+00:00", "Z"),
            "service": "Ruutu+", "channel": None, "free": False,
            "language": "fi" if fi else "en",
            "url": "https://www.ruutu.fi" + c["href"],
            "source_id": c["href"],
        })
    return events


def fetch(*, today: date) -> list[dict]:
    return parse(request(URL, headers={"Accept": "text/html"}), today=today)
