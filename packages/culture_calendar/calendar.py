"""Upsert only owned culture records; preserve unrelated calendar entries and settings."""

import datetime as dt
import time
from pathlib import Path

from movie_calendar.google_calendar import GoogleCalendar
from movie_calendar.storage import write_json

from .model import google_body


def same(old: dict, body: dict) -> bool:
    for key, value in body.items():
        if key in {"start", "end"}:
            if "date" in value:
                if old.get(key, {}).get("date") != value["date"]:
                    return False
            else:
                try:
                    if dt.datetime.fromisoformat(old[key]["dateTime"]) != dt.datetime.fromisoformat(
                        value["dateTime"]
                    ):
                        return False
                except (KeyError, ValueError):
                    return False
        elif old.get(key) != value:
            return False
    return True


class CultureCalendar(GoogleCalendar):
    def __init__(self, config: dict, state: Path):
        super().__init__(config["calendar_id"], config["subject"], config["service_account"])
        calendar = self.service.calendars().get(calendarId=self.calendar_id).execute()
        if calendar.get("summary", "").strip() != config["name"].strip():
            raise ValueError("Calendar name does not match configured culture destination")
        self.state = state

    def plan(self, events: list[dict], ledger: dict) -> list[dict]:
        current, page = {}, None
        while True:
            result = (
                self.service.events()
                .list(
                    calendarId=self.calendar_id, maxResults=2500, showDeleted=True, pageToken=page
                )
                .execute()
            )
            for e in result.get("items", []):
                uid = e.get("iCalUID")
                if uid and uid.startswith("culture-") and uid.endswith("@benjaminos"):
                    if uid in current:
                        raise ValueError("Duplicate iCalUID in target calendar")
                    current[uid] = e
            page = result.get("nextPageToken")
            if not page:
                break
        changes = []
        for e in events:
            body = google_body(e)
            old = current.get(e["uid"])
            if (old and old.get("status") == "cancelled") or (not old and e["uid"] in ledger):
                action = "skip_removed"
            else:
                action = "unchanged" if old and same(old, body) else "update" if old else "create"
            changes.append(
                dict(action=action, uid=e["uid"], body=body, event_id=old["id"] if old else None)
            )
        return changes

    def apply(self, changes: list[dict], ledger: dict) -> None:
        pending = [c for c in changes if c["action"] in {"create", "update"}]
        for offset in range(0, len(pending), 25):
            errors = []

            def completed(request_id, response, exception, batch_errors=errors):
                if exception:
                    batch_errors.append(exception)
                else:
                    ledger[request_id] = response["id"]
                    write_json(self.state / "google-ledger.json", ledger)

            batch = self.service.new_batch_http_request(callback=completed)
            for change in pending[offset : offset + 25]:
                if change["action"] == "create":
                    request = self.service.events().import_(
                        calendarId=self.calendar_id,
                        body={
                            **change["body"],
                            "iCalUID": change["uid"],
                            "reminders": {"useDefault": False},
                        },
                    )
                else:
                    body = dict(change["body"])
                    for key in ("start", "end"):
                        body[key] = {"date": None, "dateTime": None, "timeZone": None, **body[key]}
                    request = self.service.events().patch(
                        calendarId=self.calendar_id,
                        eventId=change["event_id"],
                        body=body,
                        sendUpdates="none",
                    )
                batch.add(request, request_id=change["uid"])
            batch.execute()
            if errors:
                raise RuntimeError(
                    f"{len(errors)} Google writes failed; successes saved. Rerun preview before retrying."
                )
            if offset + 25 < len(pending):
                time.sleep(3)
