# apps/morning-artifact

The 7-panel quiet morning artifact (Linear: BEN-19).

## What it is

An HTML artifact rendered every morning at 07:00 Lisbon, showing Benjamin a fixed 7-panel layout drawn from the BenjaminOS shared substrate:

```
┌──────────────┬──────────────┬──────────────┐
│ PRIORITIES   │ CALENDAR     │ PRACTICE/    │
│ (Linear)     │ (gcal)       │ HABITS       │
│              │              │ (Supabase)   │
├──────────────┴──────────────┼──────────────┤
│ RADAR                       │ INSPIRATION  │
│ (Linear, broader scope)     │ (GBrain)     │
├─────────────┬───────────────┴──────────────┤
│ IDEAS       │ PEOPLE                       │
│ (Wiki)      │ (Wiki + GBrain)              │
└─────────────┴──────────────────────────────┘
```

**Aesthetic constraints** (from `Shared drives/BenjaminOS/6-Wiki/wiki/synthesis/pharoah-daily-rearchitecture-vision-2026-05.md`): Rams · Hara · Atomic Habits · Dzogchen · Rubin · Miyazaki. Quiet, predictable, solid. Make space, don't fill space.

## Planned files

- `render.py` — main entry point, orchestrates panel data fetches + HTML output
- `panels/priorities.py` — Linear today's priorities + Pharoah ranking
- `panels/calendar.py` — Google Calendar events
- `panels/practice.py` — Habit tracker from Supabase
- `panels/radar.py` — broader Linear backlog with priority signaling
- `panels/inspiration.py` — GBrain query for "what Ben's in a lane on"
- `panels/ideas.py` — recent wiki ideas
- `panels/people.py` — recently-mentioned people from Wiki + GBrain
- `templates/morning.html` — Jinja template using `Shared drives/BenjaminOS/3-Resources/design/pharoah-design.css`
- `output/` — Rendered HTML lands here, mirrored to wiki for archival

## Schedule

Cron: `30 6 * * *` (06:30 Lisbon) — defined in `infrastructure/cron/morning-artifact.cron`.
Hermes' built-in cron can also drive this; see `infrastructure/cron/README.md`.

## Status

Not yet built. Tracking issue: BEN-19.
