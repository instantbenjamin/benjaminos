"""Cinemateca HTML extraction and RFC 5545 calendar serialization."""

import datetime as dt
import hashlib
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = "https://www.cinemateca.pt/Programacao.aspx"


class Node:
    def __init__(self, tag: str = "", attrs: tuple = ()) -> None:
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self) -> str:
        return " ".join(
            " ".join(c.text() if isinstance(c, Node) else c for c in self.children).split()
        )

    def find(self, cls: str | None = None, tag: str | None = None) -> list["Node"]:
        result = []
        for child in self.children:
            if isinstance(child, Node):
                if (cls is None or cls in child.attrs.get("class", "").split()) and (
                    tag is None or child.tag == tag
                ):
                    result.append(child)
                result.extend(child.find(cls, tag))
        return result


class Tree(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, value: str) -> None:
        self.stack[-1].children.append(value)


def fetch(url: str, cache: Path, ttl: int = 3600) -> Node:
    """Cache only validated public programme pages; expire after one hour."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + ".html")
    if not path.exists() or time.time() - path.stat().st_mtime >= ttl:
        request = Request(url, headers={"User-Agent": "BenjaminOS-Cinemateca/1.0"})
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8-sig")
        if "sectionLayoutProgram" not in html:
            raise ValueError("Unexpected programme response: " + url)
        path.write_text(html, encoding="utf-8")
        time.sleep(0.4)
    return Tree(path.read_text(encoding="utf-8")).root


def first(node: Node, cls: str) -> str:
    found = node.find(cls)
    return found[0].text() if found else ""


def extract(root: Node, source: str) -> list[dict]:
    cards = root.find("lista")
    details = root.find("infoDetail")
    if len(cards) != len(details):
        raise ValueError("Listing/detail mismatch: " + source)
    ids = []
    for link in root.find(tag="a"):
        href = link.attrs.get("href", "")
        if link.find("lista"):
            ids.append(parse_qs(urlparse(href).query)["id"][0])
    if len(ids) != len(details):
        raise ValueError("Missing screening identifiers")
    events = []
    for ident, detail in zip(ids, details, strict=True):
        stamp = first(detail, "infoDate")
        date, room = stamp.split(" | ", 1)
        start = dt.datetime.strptime(date, "%d/%m/%Y, %Hh%M").replace(
            tzinfo=ZoneInfo("Europe/Lisbon")
        )
        biblios = [x.text() for x in detail.find("infoBiblio") if x.text()]
        texts = [x.text() for x in detail.find("infoText") if x.text()]
        title = first(detail, "infoTitleProg")
        # Do not mistake an individual short's runtime for the whole programme.
        total = re.search(r"Duração total[^:]*:\s*(\d+)\s*min", " ".join(texts), re.I)
        runtime = re.search(r"\b(\d+)\s*min\b", " ".join(biblios)) if "|" not in title else None
        minutes = int((total or runtime).group(1)) if total or runtime else None
        year = re.search(r"\b((?:18|19|20)\d{2})\s*[-–]", " ".join(biblios))
        links = [urljoin(source, a.attrs.get("href", "")) for a in detail.find(tag="a")]
        dates = detail.find("infoDate")
        events.append(
            dict(
                id=ident,
                title=title,
                start=start.isoformat(),
                room=room,
                cycle=dates[1].text() if len(dates) > 1 else "",
                translated_title=first(detail, "infoTitle"),
                director=next((s[3:] for s in biblios if s.startswith("de ")), None),
                year=int(year.group(1)) if year else None,
                runtime_minutes=minutes,
                projection_notes=next((s for s in texts if len(s) < 250), None),
                multiple_films="|" in title,
                url=source + ("&" if "?" in source else "?") + "id=" + ident,
                tickets=next((s for s in links if "cinemateca.bol.pt/" in s), None),
                source_page=source,
            )
        )
    return events


def escape(value: object) -> str:
    return (
        str(value)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def fold(line: str) -> str:
    lines, chunk = [], ""
    for char in line:
        if len((chunk + char).encode()) > 75:
            lines.append(chunk)
            chunk = " "
        chunk += char
    return "\r\n".join(lines + [chunk])


def calendar(events: list[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Personal Movie Calendar//Cinemateca Snapshot//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Cinemateca",
        "X-WR-TIMEZONE:Europe/Lisbon",
    ]
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    for event in events:
        start = dt.datetime.fromisoformat(event["start"]).astimezone(dt.UTC)
        description = [event["cycle"], event["projection_notes"] or "", event["url"]]
        if event["tickets"]:
            description.append("Tickets: " + event["tickets"])
        description.append(
            "End time uses projection runtime; introductions and discussions may extend the session."
            if event["runtime_minutes"]
            else "End time unavailable; no duration has been assumed."
        )
        lines += [
            "BEGIN:VEVENT",
            "UID:cinemateca-" + event["id"] + "@personal-movie-calendar",
            "DTSTAMP:" + stamp,
            "DTSTART:" + start.strftime("%Y%m%dT%H%M%SZ"),
        ]
        if event["runtime_minutes"]:
            lines.append(
                "DTEND:"
                + (start + dt.timedelta(minutes=event["runtime_minutes"])).strftime(
                    "%Y%m%dT%H%M%SZ"
                )
            )
        lines += [
            "SUMMARY:" + escape(event["title"]),
            "LOCATION:" + escape("Cinemateca Portuguesa — " + event["room"]),
            "URL:" + event["url"],
            "DESCRIPTION:" + escape("\n".join(s for s in description if s)),
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    return "\r\n".join(fold(line) for line in lines + ["END:VCALENDAR"]) + "\r\n"


def scrape(cache: Path, from_date: str, ttl: int = 3600) -> dict:
    """Read every page of every cycle linked from the programme homepage.

    A malformed or incomplete crawl raises before any downstream writes.
    Missing screenings are never interpreted as cancellations.
    """
    dt.date.fromisoformat(from_date)
    root = fetch(BASE, cache, ttl)
    cycles = sorted(
        {
            parse_qs(urlparse(a.attrs.get("href", "")).query)["ciclo"][0]
            for a in root.find(tag="a")
            if "ciclo" in parse_qs(urlparse(a.attrs.get("href", "")).query)
        }
    )
    if not cycles or any(not cycle.isdigit() for cycle in cycles):
        raise ValueError("No valid programme cycles discovered")
    events, pages = {}, []
    for cycle in cycles:
        first_url = BASE + "?ciclo=" + cycle
        tree = fetch(first_url, cache, ttl)
        last = max(
            [1]
            + [
                int(parse_qs(urlparse(a.attrs.get("href", "")).query).get("page", ["1"])[0])
                for block in tree.find("sectionPagination")
                for a in block.find(tag="a")
            ]
        )
        if last > 100:
            raise ValueError("Unexpected pagination count")
        for page in range(1, last + 1):
            url = first_url if page == 1 else first_url + "&page=" + str(page)
            data = tree if page == 1 else fetch(url, cache, ttl)
            batch = extract(data, url)
            if not batch:
                raise ValueError("Empty cycle page: " + url)
            for event in batch:
                previous = events.get(event["id"])
                if previous and (previous["start"], previous["title"]) != (
                    event["start"],
                    event["title"],
                ):
                    raise ValueError("Conflicting screening ID: " + event["id"])
                events[event["id"]] = event
            pages.append(url)
    upcoming = sorted(
        (e for e in events.values() if e["start"][:10] >= from_date),
        key=lambda e: (e["start"], e["room"]),
    )
    return {
        "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
        "from_date": from_date,
        "cycles": cycles,
        "pages": pages,
        "scope": "Current linked cycles; not independently reconciled with monthly PDF or day view.",
        "total_screenings": len(events),
        "upcoming_screenings": upcoming,
    }
