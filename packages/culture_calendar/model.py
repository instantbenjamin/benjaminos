"""Normalized culture events, conservative duplicate detection and iCalendar output."""

import datetime as dt
import hashlib
import html
import re
import unicodedata
from zoneinfo import ZoneInfo

LISBON = ZoneInfo("Europe/Lisbon")


def text(value: object) -> str:
    if isinstance(value, list):
        value = "\n".join(str(x) for x in value)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def normal(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        unicodedata.normalize("NFKD", text(value)).encode("ascii", "ignore").decode().lower(),
    ).strip()


def timestamp(value: str) -> str:
    date = dt.datetime.fromisoformat(value)
    if date.tzinfo is None:
        date = date.replace(tzinfo=LISBON)
    return date.astimezone(LISBON).isoformat()


def event(
    source: str,
    identity: str,
    title: str,
    start: str,
    end: str,
    venue: str,
    url: str,
    *,
    all_day: bool = False,
    notes: str = "",
) -> dict:
    if all_day:
        dt.date.fromisoformat(start)
        dt.date.fromisoformat(end)
    else:
        start, end = timestamp(start), timestamp(end)
    if end <= start:
        raise ValueError("Event end must follow start")
    key = f"{source}:{identity}"
    return dict(
        key=key,
        uid="culture-" + hashlib.sha256(key.encode()).hexdigest()[:32] + "@benjaminos",
        source=source,
        title=text(title),
        start=start,
        end=end,
        all_day=all_day,
        venue=text(venue),
        url=url,
        notes=text(notes),
    )


def venue_key(value: str) -> str:
    v = normal(value)
    if any(x in v for x in ("gulbenkian", "grande auditorio", "auditorio 2", "cam centro")):
        return "gulbenkian"
    if any(x in v for x in ("ccb", "centro cultural de belem")):
        return "ccb"
    return v


def deduplicate(events: list[dict]) -> tuple[list[dict], list[dict]]:
    """Exact title/venue/date matches only. Direct venue records take priority."""
    selected, duplicates = [], []
    for e in sorted(events, key=lambda x: (x["source"] == "agendalx", x["key"])):
        match = next(
            (
                old
                for old in selected
                if normal(old["title"]) == normal(e["title"])
                and venue_key(old["venue"]) == venue_key(e["venue"])
                and old["start"] == e["start"]
                and old["all_day"] == e["all_day"]
            ),
            None,
        )
        if match:
            duplicates.append({"kept": match["key"], "skipped": e["key"]})
        else:
            selected.append(e)
    if len({x["uid"] for x in selected}) != len(selected):
        raise ValueError("Duplicate source identity")
    return sorted(selected, key=lambda x: (x["start"], x["title"])), duplicates


def description(e: dict) -> str:
    return "\n".join(filter(None, [e.get("notes"), "Programme: " + e["source"], e["url"]]))


def google_body(e: dict) -> dict:
    field = "date" if e["all_day"] else "dateTime"
    return {
        "summary": e["title"],
        "start": {field: e["start"]},
        "end": {field: e["end"]},
        "location": e["venue"],
        "description": description(e),
        "transparency": "transparent",
    }


def ical(events: list[dict]) -> str:
    def escape(s: str) -> str:
        return s.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")

    def fold(line: str) -> list[str]:
        chunks, current = [], ""
        for c in line:
            if len((current + c).encode()) > 75:
                chunks.append(current)
                current = " "
            current += c
        return chunks + [current]

    now = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BenjaminOS//Lisbon Culture//EN",
        "X-WR-CALNAME:Lisbon Culture Vulture",
        "CALSCALE:GREGORIAN",
    ]
    for e in events:
        lines += ["BEGIN:VEVENT", "UID:" + e["uid"], "DTSTAMP:" + now]
        for prop, field in [("DTSTART", "start"), ("DTEND", "end")]:
            if e["all_day"]:
                lines.append(prop + ";VALUE=DATE:" + e[field].replace("-", ""))
            else:
                value = dt.datetime.fromisoformat(e[field]).astimezone(dt.UTC)
                lines.append(prop + ":" + value.strftime("%Y%m%dT%H%M%SZ"))
        lines += [
            "SUMMARY:" + escape(e["title"]),
            "LOCATION:" + escape(e["venue"]),
            "DESCRIPTION:" + escape(description(e)),
            "URL:" + e["url"],
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in fold(line)) + "\r\n"
