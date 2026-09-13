"""Plan and upsert by iCalUID, including events previously imported from an ICS."""

import datetime as dt
import json
import os


def uid(event: dict) -> str:
    return f"cinemateca-{event['id']}@personal-movie-calendar"


def event_body(event: dict) -> dict:
    if not event.get("runtime_minutes") or event["runtime_minutes"] <= 0:
        raise ValueError("Google Calendar needs a reviewed duration")
    start = dt.datetime.fromisoformat(event["start"])
    return {
        "summary": event["title"],
        "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Lisbon"},
        "end": {
            "dateTime": (start + dt.timedelta(minutes=event["runtime_minutes"])).isoformat(),
            "timeZone": "Europe/Lisbon",
        },
        "location": "Cinemateca Portuguesa — " + event["room"],
        "description": "\n".join(
            filter(
                None,
                [
                    event.get("cycle"),
                    event.get("projection_notes"),
                    event["url"],
                    "Tickets: " + event["tickets"] if event.get("tickets") else None,
                    "End time uses projection runtime; introductions and discussions may extend the session.",
                ],
            )
        ),
        "transparency": "transparent",
    }


def equivalent(current: dict, desired: dict) -> bool:
    for name, value in desired.items():
        if name in ("start", "end"):
            try:
                if dt.datetime.fromisoformat(
                    current[name]["dateTime"]
                ) != dt.datetime.fromisoformat(value["dateTime"]):
                    return False
            except (KeyError, ValueError):
                return False
        elif current.get(name) != value:
            return False
    return True


class GoogleCalendar:
    def __init__(self, calendar_id: str, subject: str, expected_service_account: str):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        if (
            not calendar_id
            or calendar_id == "primary"
            or not subject
            or not expected_service_account
        ):
            raise ValueError(
                "Configure a dedicated calendar ID, explicit Google subject and service-account email"
            )
        scopes = ["https://www.googleapis.com/auth/calendar"]
        if os.environ.get("BENJAMINOS_SA_JSON"):
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(os.environ["BENJAMINOS_SA_JSON"]), scopes=scopes
            )
        else:
            credentials = service_account.Credentials.from_service_account_file(
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=scopes
            )
        if credentials.service_account_email != expected_service_account:
            raise ValueError("Google credentials do not match the configured service account")
        self.service = build(
            "calendar", "v3", credentials=credentials.with_subject(subject), cache_discovery=False
        )
        self.calendar_id = calendar_id
        calendar = self.service.calendars().get(calendarId=calendar_id).execute()
        if calendar.get("timeZone") != "Europe/Lisbon":
            raise ValueError("Target calendar must use Europe/Lisbon")

    def plan(self, events: list[dict]) -> list[dict]:
        changes = []
        for event in events:
            if not event.get("runtime_minutes"):
                changes.append({"action": "review", "uid": uid(event), "reason": "Missing runtime"})
                continue
            body = event_body(event)
            found, page = [], None
            while True:
                result = (
                    self.service.events()
                    .list(
                        calendarId=self.calendar_id,
                        iCalUID=uid(event),
                        showDeleted=True,
                        pageToken=page,
                    )
                    .execute()
                )
                found.extend(result.get("items", []))
                page = result.get("nextPageToken")
                if not page:
                    break
            if len(found) > 1:
                raise ValueError("Duplicate existing iCalUID; resolve before syncing")
            old = found[0] if found else None
            if old and old.get("status") == "cancelled":
                action = "skip_cancelled"
            else:
                action = (
                    "unchanged" if old and equivalent(old, body) else "update" if old else "create"
                )
            changes.append(
                {
                    "action": action,
                    "uid": uid(event),
                    "event_id": old["id"] if old else None,
                    "body": body,
                }
            )
        return changes

    def apply(self, changes: list[dict]) -> None:
        for change in changes:
            if change["action"] == "create":
                self.service.events().import_(
                    calendarId=self.calendar_id,
                    body={
                        **change["body"],
                        "iCalUID": change["uid"],
                        "reminders": {"useDefault": False},
                    },
                ).execute()
            elif change["action"] == "update":
                self.service.events().patch(
                    calendarId=self.calendar_id,
                    eventId=change["event_id"],
                    body=change["body"],
                    sendUpdates="none",
                ).execute()
