# BenjaminOS Architecture

**Status:** living doc. Updated as the system evolves.
**Last revised:** 2026-05-06

## The four layers

```
┌────────────────────────────────────────────────────────────┐
│  CAPTURE                                                    │
│  Voicenotes (Obsidian sync) · Notability OCR · iOS Reminders│
│  Telegram-Pharoah-Hermes · Cowork chat · Linear directly    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────┐
│  ROUTE — Pharoah classifier (this repo, packages/pharoah/)  │
│  Decides: task / idea / journal / habit-log / signal        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  STORE — TASKS   │ │  STORE — KNOWLEDGE│ │  STORE — OPERATNL│
│  Linear           │ │  Wiki + GBrain   │ │  Supabase public.*│
│  (workspace EIR,  │ │  (Drive 6-Wiki/, │ │  daily_logs       │
│   teams Benjamin  │ │   gbrain.* schema)│ │  habits           │
│   + EIR)          │ │                  │ │  health_snapshots │
└──────────────────┘ └──────────────────┘ │  pharoah_messages │
                                          └──────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────┐
│  RENDER — Morning artifact, daily brief, ad-hoc queries     │
│  apps/morning-artifact/ — 7-panel HTML at 7AM Lisbon         │
│  Pharoah surfaces respond to queries pulling from all stores │
└─────────────────────────────────────────────────────────────┘
```

## Pharoah surfaces

Same identity (canonical at `5-System/agent/SKILL.md`), different runtimes:

| Surface | Where it runs | Best for |
|---|---|---|
| **Cowork-Pharoah** | Mac, Cowork app | Ideation, planning, file creation, complex MCP work |
| **Claude Code-Pharoah** | Mac (CLI), or VPS | Implementing Linear issues — multi-file refactors, real coding |
| **Hermes-Pharoah** | VPS (`~/.hermes/`) Telegram gateway | Always-on capture, voice, daily brief, on-the-go queries |
| **Paperclip-Pharoah** | VPS (Paperclip multi-agent platform) | Background jobs, scheduled work, cross-agent coordination |
| **Claude.ai-Pharoah** | Web | Ad-hoc one-off queries when other surfaces aren't convenient |

All read from / write to the same shared substrate (Supabase + Drive + Linear). Coordination via `pharoah_messages` table.

## Shared substrate

| | |
|---|---|
| **Knowledge** | Drive `6-Wiki/` (markdown, canonical) + GBrain index (vectors over the wiki, on Supabase `gbrain.*` schema) |
| **Tasks** | Linear (workspace `expertsinresidence`, teams `Benjamin` and `EIR`) |
| **Operational data** | Supabase `public.*` — habits, daily_logs, health_snapshots, pharoah_messages, projects, entries |
| **Identity** | `5-System/agent/SKILL.md` (Drive, canonical) — mirrored as compressed `SOUL.md` to Hermes |
| **Secrets** | Infisical (project `pharoah`, env `dev`) |

## Data flow examples

### Voice memo → Linear task

1. Benjamin records voice memo in Voicenotes.com
2. Voicenotes Sync Obsidian plugin writes markdown to `Drive 6-Wiki/raw/personal/voicenotes/`
3. Daily `wiki-sync.sh` rclone-copies Drive → `~/wiki/` on VPS
4. Pharoah classifier (cron job, this repo) detects new file, classifies as task
5. Classifier creates Linear issue via Linear API
6. Telegram-Pharoah-Hermes confirms: "filed as BEN-XXX"

### Morning brief

1. 06:30 Lisbon — `~/bin/wiki-sync.sh` refreshes ~/wiki
2. 06:45 — GBrain incremental embed on new wiki content
3. 07:00 — `apps/morning-artifact/render.py` queries Linear (today's priorities), Supabase (habits/health), GBrain (this-week-themes), wiki (ideas in flight)
4. Renders 7-panel HTML to `~/wiki/raw/personal/daily-briefs/2026-MM-DD.html`
5. Telegram-Pharoah sends Benjamin the link + a 3-sentence summary

## Repo's role

The behaviors above are this repo's job. Drive is content; Linear is task state; Supabase is data; this repo is the *orchestration*.

## Open architectural questions

- GBrain MECE schema migration (people/companies/deals/meetings/) — deferred (BEN-54) until content density justifies the split
- Public-schema RLS gap on 18 tables (BEN-52) — separate session
- ClickUp drain pattern — when do we close the legacy workspace? (BEN-18)
- 3D brain visualization for the morning artifact — future, post-MVP

See Linear `BenjaminOS` project for live status of all of the above.
