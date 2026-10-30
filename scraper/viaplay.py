"""Viaplay's public schedule API (the same JSON the viaplay.fi sports pages use).

Endpoint: https://content.viaplay.fi/pcdash-fi/<path>?date=YYYY-MM-DD
The response links to the following days in _links["viaplay:days"].
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from .http import get_json

API_BASE = "https://content.viaplay.fi/pcdash-fi/"
WEB_BASE = "https://viaplay.fi/"
API_HOST = "content.viaplay.fi"

# Explicit language words beat commentator-name heuristics; English is checked first.
_EN = re.compile(r"selostus\W{0,3}(?:on\s+)?(?:englanti|englanniksi|englanninkiel|english)"
                 r"|englanninkielinen\s+selostus|english\s+commentary|\bin\s+english\b"
                 r"|kansainvälinen\s+selostus|alkuperäis\w*\s+selostus", re.I)
_FI_EXPLICIT = re.compile(r"selostus\W{0,3}(?:on\s+)?(?:suomi|suomeksi|suomenkiel)|suomenkielinen\s+selostus", re.I)
# "Selostus Antti Mäkinen" / "selostajana Antti Mäkinen": a named Finnish commentator.
_FI_NAME = re.compile(r"\b(?i:selostus|selostaja(?:na)?|selostajat)\W{0,3}[A-ZÅÄÖ][a-zåäö]+\s+[A-ZÅÄÖ][a-zåäö-]+")
DISCOVERED: dict[str, str] = {}


def _iso(value: str) -> str | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (AttributeError, ValueError):
        return None


def _strings(value, out: list[str]) -> list[str]:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _strings(v, out)
    elif isinstance(value, list):
        for v in value:
            _strings(v, out)
    return out


def _text(product: dict) -> str:
    content = product.get("content", {})
    return " ".join(_strings(content.get("description", {}), []) + _strings(content.get("synopsis", ""), []))


def explain_language(product: dict) -> tuple[str | None, str]:
    """Best-effort commentary language and the rule that decided it.

    Only fields that clearly describe the audio track count as explicit; a generic
    `languages` field lists the service's UI languages and is ignored.
    """
    content = product.get("content", {})
    for key in ("audioLanguages", "commentaryLanguages", "audioTracks"):
        langs = content.get(key) or product.get(key)
        if isinstance(langs, list) and langs:
            codes = {str(l.get("code", l.get("language", "")) if isinstance(l, dict) else l).lower()[:2] for l in langs}
            if "fi" in codes:
                return "fi", f"field:{key}"
            if "en" in codes:
                return "en", f"field:{key}"
    text = _text(product)
    if _EN.search(text):
        return "en", "text:english"
    if _FI_EXPLICIT.search(text):
        return "fi", "text:finnish"
    if _FI_NAME.search(text):
        return "fi", "text:commentator"
    return None, "none"


def detect_language(product: dict) -> str | None:
    return explain_language(product)[0]


def iter_products(node):
    if isinstance(node, dict):
        if node.get("type") == "sport" and isinstance(node.get("epg"), dict):
            yield node
        for v in node.values():
            yield from iter_products(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_products(v)


def parse_day(raw: dict, *, sport: str, fmt: str | None, extra_feeds: set[str]) -> list[dict]:
    if not isinstance(raw, dict) or "_embedded" not in raw:
        raise ValueError("Viaplayn vastauksen rakenne muuttui (_embedded puuttuu)")
    events = []
    for p in iter_products(raw["_embedded"]):
        content = p.get("content", {})
        title = (content.get("title") or "").strip()
        series = (content.get("format") or {}).get("title")
        if fmt and series != fmt:
            continue
        if title in extra_feeds or (content.get("originalTitle") or "").strip() == "Studio":
            continue
        flags = (p.get("system") or {}).get("flags") or []
        airing = (p.get("recording") or {}).get("airingType")
        live = "liveStream" in flags or airing == "live"
        if airing and airing != "live":
            continue  # replays / highlights
        start, end = _iso(p["epg"].get("start")), _iso(p["epg"].get("end"))
        if not start or not live:
            continue
        session = (content.get("originalTitle") or content.get("episodeTitle")
                   or (content.get("description") or {}).get("synopsis") or "")
        if session == title:
            session = ""
        path = p.get("publicPath")
        lang, why = explain_language(p)
        events.append({
            "sport": sport,
            "series": series or fmt,
            "title": title,
            "session": session.strip()[:80],
            "start": start,
            "end": end,
            "service": "Viaplay",
            "channel": None,
            "free": False,
            "language": lang,
            "language_rule": why,
            "language_sample": _text(p)[:160],
            "url": f"{WEB_BASE}urheilu/{path}" if path and not path.startswith("urheilu/") else (f"{WEB_BASE}{path}" if path else WEB_BASE + "urheilu"),
            "source_id": (p.get("system") or {}).get("guid"),
        })
    return events


def day_links(raw: dict) -> list[dict]:
    links = (raw.get("_links") or {}).get("viaplay:days") or []
    return [l for l in links if isinstance(l, dict) and l.get("date") and l.get("href")]


def discover_path(keyword: str) -> str:
    """Find a sport path (e.g. darts) from the sports landing page links."""
    raw = get_json(API_BASE + "urheilu")
    hrefs = set()

    def walk(node):
        if isinstance(node, dict):
            href = node.get("href")
            if isinstance(href, str) and API_HOST in href and keyword in href.lower():
                hrefs.add(urlparse(href).path)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw)
    if not hrefs:
        raise RuntimeError(f"Viaplaysta ei löytynyt polkua lajille '{keyword}'")
    # shortest path = the sport landing page, not a single event
    path = min(hrefs, key=len)
    return path.split("/pcdash-fi/", 1)[1]


def fetch(sport: str, cfg: dict, *, first_date: str, last_date: str, extra_feeds: set[str]) -> list[dict]:
    path = cfg.get("path") or discover_path(cfg["discover"])
    DISCOVERED[sport] = path
    first = get_json(f"{API_BASE}{path}?date={first_date}")
    events = parse_day(first, sport=sport, fmt=cfg.get("format"), extra_feeds=extra_feeds)
    for link in day_links(first):
        if not (first_date < link["date"] <= last_date):
            continue
        if urlparse(link["href"]).hostname != API_HOST:
            raise RuntimeError("Tuntematon Viaplayn päiväosoite")
        events += parse_day(get_json(link["href"]), sport=sport, fmt=cfg.get("format"), extra_feeds=extra_feeds)
    return events
