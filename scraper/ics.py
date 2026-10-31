"""One iCalendar file per event, with an alarm before the start (RFC 5545).

Opening https://.../ics/<id>.ics on an iPhone shows the event with "Add to Calendar".
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

PRODID = "-//primetimesports//Ruutuaikataulu//FI"


def _esc(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold to 75 octets per line without splitting a UTF-8 character."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def _dt(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def event_ics(ev: dict, sport_name: str, *, now: datetime, alarm_minutes: int = 15) -> str:
    services = ", ".join(dict.fromkeys(b["service"] for b in ev["broadcasts"] if b.get("service")))
    free = [b["service"] for b in ev["broadcasts"] if b.get("free")]
    primary = next((b for b in ev["broadcasts"] if b.get("free")), ev["broadcasts"][0] if ev["broadcasts"] else {})
    summary = f'{ev.get("series") or sport_name}: {ev["title"]}' + (f' – {ev["session"]}' if ev.get("session") else "")
    desc = [f"Missä: {services}" if services else ""]
    if free:
        desc.append("Ilmaiskanava: " + ", ".join(dict.fromkeys(free)))
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f'UID:{ev["id"]}@primetimesports',
        f"DTSTAMP:{now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f'DTSTART:{_dt(ev["start"])}',
        f'DTEND:{_dt(ev["end"])}',
        f"SUMMARY:{_esc(summary)}",
        f"LOCATION:{_esc(services)}",
        f"DESCRIPTION:{_esc(chr(10).join(d for d in desc if d))}",
    ]
    if primary.get("url"):
        lines.append(f'URL:{primary["url"]}')
    lines += [
        "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(summary)}",
        f"TRIGGER:-PT{int(alarm_minutes)}M", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def write_all(events: list[dict], sports: dict[str, str], out_dir: Path, *, now: datetime) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.ics"):
        old.unlink()
    for ev in events:
        (out_dir / f'{ev["id"]}.ics').write_bytes(
            event_ics(ev, sports.get(ev["sport"], ev["sport"]), now=now).encode("utf-8"))
    return len(events)
