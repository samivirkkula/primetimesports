"""MTV's public TV-guide GraphQL API (used by mtv.fi/kanavat/aikataulu).

Only LIVE programmes on the free-to-air channels MTV3 and Sub are used:
they mark free Liiga games and the weekly NHL game on Sub.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

from .http import post_json, request

API = "https://nordic-gateway.mtv.a2d.tv/graphql"
GUIDE = "https://www.mtv.fi/kanavat/aikataulu"
CHANNELS = {"MTV3": re.compile(r"^MTV ?3$", re.I), "MTV Sub": re.compile(r"^(MTV )?SUB$", re.I)}

EPG_QUERY = """query Epg($id: ID!, $date: Date) {
  media(id: $id) { ... on Channel {
    id epg(fullBroadcastDay: true, date: $date) { broadcastId title start end type }
  } }
}"""


class _Client:
    def __init__(self):
        self.version = os.environ.get("MTV_CLIENT_VERSION", "5.5.0")

    def query(self, query: str, variables: dict | None = None) -> dict:
        res = post_json(API, {"query": query, "variables": variables or {}},
                        headers={"client-name": "mtv-web", "client-version": self.version})
        if res.get("errors"):
            raise RuntimeError("; ".join(e.get("message", "?") for e in res["errors"]))
        return res

    def discover_version(self) -> None:
        html = request("https://www.mtv.fi/kanavat")
        for src in re.findall(r'src="(/_next/static/chunks/[^"]+\.js)"', html):
            m = re.search(r'name:"web",version:"([\d.]+)"', request("https://www.mtv.fi" + src))
            if m:
                self.version = m.group(1)
                return
        raise RuntimeError("MTV:n web-asiakkaan versiota ei löytynyt")


def parse_epg(raw: dict, channel: str) -> list[dict]:
    epg = (((raw or {}).get("data") or {}).get("media") or {}).get("epg")
    if not isinstance(epg, list):
        raise ValueError("MTV:n ohjelmaoppaan rakenne muuttui")
    out = []
    for e in epg:
        if e.get("type") != "LIVE" or not e.get("start"):
            continue
        out.append({"title": e.get("title", ""), "start": _iso(e["start"]),
                    "end": _iso(e.get("end")), "channel": channel})
    return out


def _iso(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        dt = datetime.fromtimestamp(v / 1000, timezone.utc)
    else:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def fetch(*, first_date: date, days: int) -> list[dict]:
    client = _Client()
    try:
        channels = client.query("query Channels { channels { id title } }")
    except RuntimeError as exc:
        if not re.search(r"version|deprecated", str(exc), re.I):
            raise
        client.discover_version()
        channels = client.query("query Channels { channels { id title } }")
    found = {}
    for c in channels["data"]["channels"]:
        for name, rx in CHANNELS.items():
            if rx.match(c.get("title", "")):
                found[name] = c["id"]
    if not found:
        raise RuntimeError("MTV3/Sub puuttuu MTV:n kanavalistasta")
    out = []
    for name, cid in found.items():
        for i in range(days):
            d = first_date + timedelta(days=i)
            # The broadcast day starts at 06:00; noon UTC selects the intended Finnish day.
            ms = int(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp() * 1000)
            out += parse_epg(client.query(EPG_QUERY, {"id": cid, "date": ms}), name)
    return out
