"""Explicit film identity mappings; never accept the first fuzzy search result."""

import re
import unicodedata


def key(film: dict) -> tuple[str, int | None, str]:
    def normalize(value: str | None) -> str:
        return re.sub(
            r"[^a-z0-9]",
            "",
            unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower(),
        )

    return normalize(film["title"]), film.get("year"), normalize(film.get("director"))


def match(events: list[dict], catalog: dict) -> tuple[list[dict], list[dict]]:
    """Return screenings with reviewed movie IDs and a separate unresolved queue."""
    known = {}
    for film in catalog["films"]:
        identity = key(film)
        if not all(identity) or not isinstance(film["trakt_id"], int) or film["trakt_id"] <= 0:
            raise ValueError("Invalid reviewed film identity")
        if identity in known and known[identity] != film["trakt_id"]:
            raise ValueError("Conflicting reviewed film identity")
        known[identity] = film["trakt_id"]
    matched, unresolved = [], []
    for event in events:
        if event["id"] in catalog.get("nonfilm_screenings", []):
            continue
        parts = catalog.get("screening_overrides", {}).get(event["id"])
        if parts is None:
            if event.get("multiple_films"):
                unresolved.append(
                    {
                        "screening_id": event["id"],
                        "title": event["title"],
                        "reason": "Multi-film programme needs individual film identities",
                    }
                )
                continue
            parts = [event]
        ids = []
        for film in parts:
            ident = known.get(key(film))
            if ident:
                ids.append(ident)
            else:
                unresolved.append(
                    {
                        "screening_id": event["id"],
                        "title": film["title"],
                        "year": film.get("year"),
                        "director": film.get("director"),
                        "reason": "No reviewed movie identity",
                    }
                )
        matched.append({**event, "trakt_ids": sorted(set(ids))})
    return matched, unresolved
