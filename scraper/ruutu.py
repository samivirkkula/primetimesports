"""Ruutu's NFL page (https://www.ruutu.fi/ohjelmat/nfl): upcoming live game streams on Ruutu+ Urheilu.

The page lists each live stream as a link to /stream/<id> with a title, a time element
("<strong>20:00</strong>1.11.") and an image whose alt text tells the commentary
language ("Selostus suomi"). RedZone and recordings are skipped.

Each card is cut out of the HTML as the text between <a href="/stream/..."> and its </a>,
so the parser does not depend on how the page nests or self-closes its tags.
"""
from __future__ import annotations

import html as htmllib
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .http import request

URL = "https://www.ruutu.fi/ohjelmat/nfl"
TZ = ZoneInfo("Europe/Helsinki")
GAME = re.compile(r".+\s(?:-|–|—|vs\.?|@)\s.+", re.I)

_CARD = re.compile(r'<a\b[^>]*\bhref="(/stream/[^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_TITLE = re.compile(r'<[a-z0-9]+\b[^>]*class="[^"]*titleText[^"]*"[^>]*>(.*?)</[a-z0-9]+>', re.S | re.I)
_TIME = re.compile(r'<[a-z0-9]+\b[^>]*class="[^"]*__time[^"]*"[^>]*>(.*?)</(?:span|div|p|time)>', re.S | re.I)
_CLOCK = re.compile(r"(\d{1,2})[:.](\d{2})(?!\d)")
_DAY = re.compile(r"(?<![\d:.])(\d{1,2})\.(\d{1,2})\.")
_ALT = re.compile(r'\balt="([^"]*)"', re.I)
_TAG = re.compile(r"<[^>]+>")
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _text(fragment: str) -> str:
    # React SSR splits text nodes with <!-- --> comments ("20<!-- -->:<!-- -->00").
    return " ".join(htmllib.unescape(_TAG.sub(" ", _COMMENT.sub("", fragment))).split())


def _event_date(day: int, month: int, today: date) -> date | None:
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if today - timedelta(days=1) <= d <= today + timedelta(days=40):
            return d
    return None


def parse_cards(html: str) -> list[dict]:
    """Raw cards: href, title, clock text, date text, image alts."""
    cards = []
    for href, body in _CARD.findall(html):
        title_m = _TITLE.search(body)
        time_m = _TIME.search(body)
        time_html = time_m.group(1) if time_m else body
        strong = re.search(r"<strong\b[^>]*>(.*?)</strong>", time_html, re.S | re.I)
        cards.append({
            "href": href,
            "title": _text(title_m.group(1)) if title_m else "",
            "clock": _text(strong.group(1)) if strong else _text(time_html),
            "time": _text(time_html),
            "alts": [htmllib.unescape(a) for a in _ALT.findall(body)],
        })
    return cards


def parse(html: str, *, today: date) -> list[dict]:
    head = _text(" ".join(re.findall(r"<(?:h1|title)\b[^>]*>(.*?)</(?:h1|title)>", html, re.S | re.I)))
    if "NFL" not in head:
        raise ValueError("Ruudun NFL-sivun rakenne muuttui (NFL-otsikko puuttuu)")
    cards = parse_cards(html)
    events = []
    for c in cards:
        title = c["title"]
        clock = _CLOCK.search(c["clock"])
        day = _DAY.search(c["time"].replace(c["clock"], " ")) or _DAY.search(c["time"])
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
            "sport": "nfl", "series": "NFL", "title": re.sub(r"\s+-\s+", " – ", title), "session": "",
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": (start + timedelta(hours=3, minutes=30)).isoformat().replace("+00:00", "Z"),
            "service": "Ruutu+", "channel": None, "free": False,
            "language": "fi" if fi else "en",
            "url": "https://www.ruutu.fi" + c["href"],
            "source_id": c["href"],
        })
    # Cards were found but none could be read: the markup changed. Fail loudly so the
    # cached result is used and the app footer reports the problem. A page with only
    # RedZone (or nothing) on it is not an error.
    titled = [c for c in cards if c["title"]]
    games = [c for c in titled if "redzone" not in c["title"].lower() and GAME.match(c["title"])]
    if (cards and not titled) or (games and not events):
        raise ValueError(f"Ruudun NFL-sivulta löytyi {len(cards)} korttia, mutta otteluita ei voitu lukea")
    return events


def fetch(*, today: date) -> list[dict]:
    return parse(request(URL, headers={"Accept": "text/html"}), today=today)
