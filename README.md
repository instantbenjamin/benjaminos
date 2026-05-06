# BenjaminOS

The codebase for **BenjaminOS** — Benjamin White's personal Chief-of-Staff system. The Pharoah agent (named after Pharoah Sanders) lives across multiple surfaces (Cowork, Claude Code, Telegram-via-Hermes, Paperclip-on-VPS) and shares this codebase as the "what runs" layer of the system.

> **The product is BenjaminOS. The agent is Pharoah. The runtime layer (for the always-on Telegram surface) is Hermes.**

## What lives where

| Layer | Location | Owns |
|---|---|---|
| **This repo** | `github.com/instantbenjamin/benjaminos` | All operational code: ingest scripts, classifiers, schedulers, app code, VPS automation, agent skills/configs |
| **Drive — `Shared drives/BenjaminOS/`** | Google Drive | Knowledge: wiki, briefs, plans, design assets, agent identity (canonical `5-System/agent/SKILL.md`) |
| **Linear — `BenjaminOS` project** | `linear.app/expertsinresidence/team/BEN` | All issues, status tracking, history of what's shipped |
| **Supabase — `BenjaminOS` project** | `yttxrgbzcvmeystoheeo` | `gbrain.*` (vector index over wiki) + `public.*` (operational tables: BuJo, habits, daily logs, pharoah_messages) |
| **Hermes runtime** | VPS at `~/.hermes/` | Always-on Pharoah surface, Telegram gateway, agent loop |

The pattern: **Drive holds what doesn't compile. This repo holds what runs.** Linear ties them together.

## Repo structure

```
benjaminos/
├── packages/
│   ├── ingest/         # Capture sync scripts (Raindrop, Readwise, Workflowy, Voicenotes)
│   ├── pharoah/        # Classifier, daily-brief renderer, twin-mind interface
│   ├── hermes/         # SOUL.md (canonical), skills, config snapshots
│   └── shared/         # Cross-package utilities: Supabase client, GBrain client, Linear client
├── apps/
│   └── morning-artifact/   # 7-panel daily HTML artifact (BEN-19)
├── infrastructure/
│   ├── vps-scripts/    # Bash scripts run on VPS (wiki-sync, gbrain-*)
│   └── cron/           # Cron specs as code
├── docs/
│   ├── architecture.md
│   └── runbooks/
└── tests/
```

## Quickstart

```bash
git clone git@github.com:instantbenjamin/benjaminos.git
cd benjaminos
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Conventions

- **Python first** (3.12+). TS/JS goes under `apps/<name>/web/` if/when needed.
- **Branch naming**: `benjamin/ben-<NNN>-<slug>` (matches Linear's `gitBranchName` field).
- **PR titles**: include `BEN-<NNN>` so Linear auto-links.
- **Secrets**: NEVER in repo. Always pulled from Infisical (`pharoah/dev` workspace) at runtime.
- **One package, one purpose.** If a thing doesn't fit, it gets its own package — don't bloat shared/.

## Where to read first if you're an AI agent

→ `CLAUDE.md` (this repo's agent context — start here)
→ `Shared drives/BenjaminOS/5-System/agent/SKILL.md` (canonical Pharoah identity)
→ Linear `BenjaminOS` project for the active task list

## License

Private — all rights reserved. Personal infrastructure.
