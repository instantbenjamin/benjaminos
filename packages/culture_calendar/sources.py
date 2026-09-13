"""Public programme readers. Raw responses stay in the private state directory."""

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from movie_calendar.storage import write_json


class Reader:
    def __init__(self, state: Path, fresh: bool = False):
        self.cache = state / "cache"
        self.fresh = fresh

    def get(self, url: str, **params: object) -> tuple[str, dict]:
        key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
        path = self.cache / (key + ".json")
        if path.exists() and not self.fresh and time.time() - path.stat().st_mtime < 3600:
            value = json.loads(path.read_text())
            return value["body"], value["headers"]
        for attempt in range(3):
            try:
                request = Request(
                    url + "?" + urlencode(params),
                    headers={"User-Agent": "BenjaminOS-CultureCalendar/0.1 (personal calendar)"},
                )
                with urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8")
                    headers = {k.lower(): v for k, v in response.headers.items()}
                break
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        value = {"body": body, "headers": headers}
        write_json(path, value)
        return body, headers

    def json(self, url: str, **params: object) -> tuple[object, dict]:
        body, headers = self.get(url, **params)
        return json.loads(body), headers


def ccb(reader: Reader, start: str, end: str) -> list[dict]:
    result = {"ccb": []}
    for page in range(1, 101):
        data, _ = reader.json(
            "https://www.ccb.pt/wp-json/tribe/events/v1/events",
            per_page=50,
            page=page,
            start_date=start,
            end_date=end,
            wpml_language="pt-pt",
        )
        result["ccb"].extend(data["events"])
        if page >= data["total_pages"]:
            break
    else:
        raise ValueError("CCB pagination exceeded limit")

    records = result["ccb"]
    if len(records) != data["total"] or len({r["id"] for r in records}) != len(records):
        raise ValueError("CCB pagination was incomplete or repeated records")
    return result["ccb"]


def gulbenkian(reader: Reader) -> list[dict]:
    result = {"gulbenkian": []}
    ids = set()
    for page in range(1, 101):
        body, headers = reader.get(
            "https://gulbenkian.pt/wp-json/fcg-content/v1/index/archive/session",
            per_page=100,
            page=page,
        )
        found = set(re.findall(r'data-event-id="(\d+)"', body))
        if not found:
            if page == 1:
                raise ValueError("Gulbenkian agenda returned no event IDs")
            break
        ids.update(found)
        total = int(headers.get("x-wp-totalpages", "0"))
        if total and page >= total:
            break
    else:
        raise ValueError("Gulbenkian pagination exceeded limit")
    ordered = sorted(ids)
    for offset in range(0, len(ordered), 50):
        data, _ = reader.json(
            "https://gulbenkian.pt/wp-json/wp/v2/events",
            include=",".join(ordered[offset : offset + 50]),
            per_page=50,
        )
        result["gulbenkian"].extend(data)
    if {str(x["id"]) for x in result["gulbenkian"]} != ids:
        raise ValueError("Gulbenkian event details incomplete")

    return result["gulbenkian"]


def agendalx(reader: Reader) -> list[dict]:
    result = {"agendalx": []}
    seen = set()
    for page in range(1, 101):
        data, _ = reader.json(
            "https://www.agendalx.pt/wp-json/agendalx/v1/events", per_page=100, page=page
        )
        if not isinstance(data, list):
            raise ValueError("AgendaLX response shape changed")
        if not data:
            break
        keys = {x["id"] for x in data}
        if keys & seen:
            raise ValueError("AgendaLX pagination repeats events")
        seen.update(keys)
        result["agendalx"].extend(data)
        if len(data) < 100:
            break
    else:
        raise ValueError("AgendaLX pagination exceeded limit")
    venues, _ = reader.json("https://www.agendalx.pt/wp-json/agendalx/v1/venues")
    cities = {v["term_id"]: v.get("meta", {}).get("_city", []) for v in venues}
    for record in result["agendalx"]:
        for venue in (record.get("venue") or {}).values():
            venue["cities"] = cities.get(venue["id"], [])
    return result["agendalx"]


def collect(reader: Reader, start: str, end: str) -> dict:
    """Independent public sites are read concurrently; any failure aborts the collection."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {
            "ccb": pool.submit(ccb, reader, start, end),
            "gulbenkian": pool.submit(gulbenkian, reader),
            "agendalx": pool.submit(agendalx, reader),
        }
        return {name: job.result() for name, job in jobs.items()}
