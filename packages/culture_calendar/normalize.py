"""Turn published dates into events; retain uncertain records for review."""

import datetime as dt
import re

from .model import deduplicate, event, normal, text


def session_times(hours: str, day: str) -> list[tuple[str, str | None]] | None:
    """Parse only complete simple time or weekday/time expressions; never partial matches."""
    weekday = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"][
        dt.date.fromisoformat(day).weekday()
    ]
    found = []
    for segment in hours.split(";"):
        segment = segment.strip().lower()
        applies = True
        if ":" in segment:
            prefix, segment = segment.split(":", 1)
            if normal(prefix) not in {"seg", "ter", "qua", "qui", "sex", "sab", "dom"}:
                return None
            applies = normal(prefix) == weekday
        match = re.fullmatch(
            r"\s*(\d{1,2})h([0-5]\d)?(?:\s*[-–]\s*(\d{1,2})h([0-5]\d)?)?\s*", segment
        )
        if not match or int(match[1]) > 23 or (match[3] and int(match[3]) > 23):
            return None
        if applies:
            found.append(
                (
                    f"{int(match[1]):02d}:{match[2] or '00'}",
                    f"{int(match[3]):02d}:{match[4] or '00'}" if match[3] else None,
                )
            )
    return sorted(set(found))


def normalize(raw: dict, start: str, end: str, excluded: list[str]) -> dict:
    events, review, skipped, exhibitions = [], [], [], {}

    def hold(source: str, record: dict, reason: str) -> None:
        review.append(
            {
                "source": source,
                "id": record.get("id"),
                "reason": reason,
                "title": text(
                    record.get("title", {}).get("rendered", "")
                    if isinstance(record.get("title"), dict)
                    else record.get("title")
                ),
                "url": record.get("url", record.get("link", "")),
            }
        )

    def excluded_record(source: str, r: dict, venue: str, title: str) -> bool:
        haystack = normal(venue + " " + title + " " + text(r.get("organizer", "")))
        if any(normal(x) in haystack for x in excluded):
            skipped.append({"source": source, "id": r["id"], "reason": "Excluded institution"})
            return True
        return False

    def add(e: dict) -> None:
        if e["end"][:10] >= start and e["start"][:10] <= end:
            events.append(e)

    for r in raw["ccb"]:
        venue_data = r.get("venue") or {}
        if not isinstance(venue_data, dict):
            hold("ccb", r, "Missing venue")
            continue
        venue = venue_data.get("venue") or "CCB — " + venue_data.get("address", "Praça do Império")
        if excluded_record("ccb", r, venue, r["title"]):
            continue
        if normal(venue_data.get("city", "")) not in {"lisboa", "lisbon"}:
            hold("ccb", r, "Venue is not confirmed in Lisbon")
            continue
        if any(word in normal(r["title"]) for word in ["festas de aniversario", "cancelad"]):
            hold("ccb", r, "Private booking offer or cancellation notice")
            continue
        categories = {x["slug"] for x in r.get("categories", [])}
        if "escolas" in categories:
            hold("ccb", r, "School-group programme; not a public performance")
            continue
        if "exposicoes" in categories or "exhibitions" in categories:
            base = re.sub(r"/\d{4}-\d{2}-\d{2}/?$", "/", r["url"])
            exhibitions.setdefault(base, []).append(r)
            continue
        duration = dt.datetime.fromisoformat(r["end_date"]) - dt.datetime.fromisoformat(
            r["start_date"]
        )
        if duration <= dt.timedelta(0) or duration > dt.timedelta(hours=6) or r.get("all_day"):
            hold(
                "ccb", r, "Listing is a broad opening/booking window; precise session needs review"
            )
            continue
        add(
            event(
                "ccb",
                str(r["id"]),
                r["title"],
                r["utc_start_date"] + "+00:00",
                r["utc_end_date"] + "+00:00",
                venue,
                r["url"],
                notes=text(r.get("excerpt")),
            )
        )
    for base, entries in exhibitions.items():
        r = entries[0]
        first = min(x["start_date"][:10] for x in entries)
        last = max(x["end_date"][:10] for x in entries)
        add(
            event(
                "ccb",
                base,
                r["title"],
                first,
                (dt.date.fromisoformat(last) + dt.timedelta(days=1)).isoformat(),
                r["venue"].get("venue") or "CCB — " + r["venue"].get("address", "Praça do Império"),
                base,
                all_day=True,
                notes="Exhibition visit window within the imported programme period; not a daily appointment. Check source for opening days and actual exhibition opening/closing dates.",
            )
        )

    for r in raw["gulbenkian"]:
        title = text(r["title"]["rendered"])
        locations = [
            x.removeprefix("locations-").replace("-", " ")
            for x in r.get("class_list", [])
            if x.startswith("locations-")
        ]
        physical = [x for x in locations if x not in {"online", "outros", "outro"}]
        if not physical or any(
            x in normal(" ".join(physical)) for x in ["paris", "londres", "porto", "oeiras"]
        ):
            hold("gulbenkian", r, "Physical Lisbon venue needs confirmation")
            continue
        venue = "Gulbenkian — " + "; ".join(physical)
        if excluded_record("gulbenkian", r, venue, title):
            continue
        sessions = r.get("sessions", {}).get("sessions", [])
        if not sessions:
            hold("gulbenkian", r, "No explicit sessions")
        for index, s in enumerate(sessions):
            if s.get("cancelled"):
                hold("gulbenkian", r, "Published cancellation; reconcile existing event manually")
                continue
            if s.get("type") == "weekly" and 9466 in r.get("fcg-agenda_template", []):
                add(
                    event(
                        "gulbenkian",
                        f"{r['id']}:exhibition",
                        title,
                        s["start"],
                        (dt.date.fromisoformat(s["end"]) + dt.timedelta(days=1)).isoformat(),
                        venue,
                        r["link"],
                        all_day=True,
                        notes="Exhibition visit window; check source for opening days and hours.",
                    )
                )
                continue
            if s.get("type") != "single" or not s.get("start") or not s.get("end"):
                hold("gulbenkian", r, "Session recurrence requires review")
                continue
            first, last = s["start"], s["end"]
            if last <= first:
                hold("gulbenkian", r, "Session lacks a valid end")
                continue
            if dt.datetime.fromisoformat(last) - dt.datetime.fromisoformat(first) > dt.timedelta(
                days=1
            ):
                hold("gulbenkian", r, "Multi-day session is not a single performance")
                continue
            acf_sessions = r.get("acf", {}).get("sessions") or []
            uuid = next(
                (
                    a.get("uuid")
                    for a in acf_sessions
                    if a.get("start_date") == first and a.get("end_date") == last
                ),
                None,
            )
            add(
                event(
                    "gulbenkian",
                    f"{r['id']}:{uuid or s.get('uuid') or index}",
                    title,
                    first,
                    last,
                    venue,
                    r["link"],
                    notes="Sold out at retrieval." if s.get("sold_out") else "",
                )
            )

    for r in raw["agendalx"]:
        title = text(r["title"]["rendered"])
        venues = list((r.get("venue") or {}).values())
        if len(venues) != 1:
            hold("agendalx", r, "Multiple or missing venues")
            continue
        venue = venues[0]["name"]
        if not any(normal(city) in {"lisboa", "lisbon"} for city in venues[0].get("cities", [])):
            hold("agendalx", r, "Venue city is not confirmed as Lisbon")
            continue
        if excluded_record("agendalx", r, venue, title):
            continue
        # Source-specific adapters already cover these institutions. Avoid language/title duplicates.
        if any(x in normal(venue) for x in ["ccb", "centro cultural de belem", "gulbenkian"]):
            skipped.append(
                {"source": "agendalx", "id": r["id"], "reason": "Covered by direct venue source"}
            )
            continue
        dates = sorted(set(r.get("occurences", [])))
        if not dates or dates[-1] < start or dates[0] > end:
            continue
        try:
            for day in dates:
                dt.date.fromisoformat(day)
        except ValueError:
            hold("agendalx", r, "Invalid occurrence date")
            continue
        hours = text(r.get("string_times"))
        notes = f"Published dates: {text(r.get('string_dates'))}. Published hours: {hours}."
        span = (dt.date.fromisoformat(dates[-1]) - dt.date.fromisoformat(dates[0])).days + 1
        if (
            r.get("subject") == "artes"
            and len(dates) >= 5
            and len(dates) / span >= 0.5
            and normal(hours) in {"", "varios horarios"}
        ):
            add(
                event(
                    "agendalx",
                    str(r["id"]),
                    title,
                    dates[0],
                    (dt.date.fromisoformat(dates[-1]) + dt.timedelta(days=1)).isoformat(),
                    venue,
                    r["link"],
                    all_day=True,
                    notes="Exhibition visit window; check opening days. " + notes,
                )
            )
            continue
        if session_times(hours, dates[0]) is None:
            hold("agendalx", r, "Precise session time needs review: " + hours)
            continue
        for day in dates:
            if not start <= day <= end:
                continue
            for time_index, (begin, finish) in enumerate(session_times(hours, day)):
                first = dt.datetime.fromisoformat(day + "T" + begin)
                last = (
                    dt.datetime.fromisoformat(day + "T" + finish)
                    if finish
                    else first + dt.timedelta(hours=1)
                )
                if last <= first:
                    last += dt.timedelta(days=1)
                add(
                    event(
                        "agendalx",
                        f"{r['id']}:{day}:{time_index}",
                        title,
                        first.isoformat(),
                        last.isoformat(),
                        venue,
                        r["link"],
                        notes=notes
                        + (
                            " End time is estimated: one hour; source gives start only."
                            if not finish
                            else ""
                        ),
                    )
                )
    selected, duplicates = deduplicate(events)
    return dict(
        events=selected,
        review=review,
        skipped=skipped,
        duplicates=duplicates,
        window={"from": start, "through": end},
        source_records={k: len(v) for k, v in raw.items()},
    )
