# Lisbon Culture Vulture

`CCB + Gulbenkian + AgendaLX → normalized events + review queue → ICS / Google Calendar`

Install from the repository with `pip install -e '.[dev,gws]'`. Set
`CULTURE_CALENDAR_CONFIG` to a private JSON file modeled on
`packages/culture_calendar/config.example.json`. Reuse the Pharoah Infisical
configuration documented in [movie-calendar.md](movie-calendar.md); only
`BENJAMINOS_SA_JSON` is retrieved. The calendar ID, delegated subject, expected
service-account email and calendar name are checked before use.

```sh
culture-calendar --config /private/path/culture.json
culture-calendar --config /private/path/culture.json --google
culture-calendar --config /private/path/culture.json --google --apply
```

Default horizon: today through 90 days ahead. `--from`, `--days`, `--fresh` and
`--snapshot` support controlled refresh and review. Public responses cache for one
hour. A failure or pagination cap aborts collection before any Google writes.

Private state files: `raw.json`, `events.json`, `calendar.ics`, `plan.json`,
`google-ledger.json`, `cache/`. Never commit these. Keep the ledger on persistent
storage so deleted Google events are not recreated. Only one process per state
directory may run; this is not a distributed lock.

CCB recurring exhibitions become an all-day visit window within the imported
period, explicitly labeled as such. Broader opening/booking windows need review.
Gulbenkian records use published session dates, not publication dates. Unsupported
recurrence shapes remain in the review queue. AgendaLX provides broad discovery;
direct venue sources take precedence. Start-only listings use a clearly labeled
one-hour estimated end. Unknown times and ambiguous venues remain for review.

New Google events have no reminders and do not block availability. Existing
reminders and unrelated fields are preserved. No calendar creation, sharing
changes, attendee invitations or Trakt list writes occur. Removed events stay
removed; source disappearances and cancellations require review. Stable UIDs
prevent duplicates on reruns; changes are verified after apply. Partial API-write
failures can be resumed after inspecting the saved plan.

This is a first adapter set, not coverage of every researched institution.
No recurring schedule or hosted iCal subscription is enabled by installation.
The same CLI can run from an agent or a scheduler after choosing a cadence.

Source endpoints and their public metadata were checked on 2026-09-13:
[CCB](https://www.ccb.pt/wp-json/tribe/events/v1/events),
[Gulbenkian](https://gulbenkian.pt/wp-json/wp/v2/events),
[AgendaLX](https://www.agendalx.pt/wp-json/agendalx/v1/events).
These are website APIs, not guaranteed integration contracts; schema changes fail
or produce review items rather than guessed calendar entries.
