# packages/hermes

Configuration and skills for the **Hermes runtime** — the Telegram-driven Pharoah surface that runs always-on on the VPS.

## What's here

- `SOUL.md` — Pharoah's compressed persona for Hermes (canonical here, deployed to VPS `~/.hermes/SOUL.md`)
- `config-snapshots/` — Periodic copies of `~/.hermes/config.yaml` for change tracking
- `skills/` — Hermes skill files (auto-loaded by Hermes when relevant). Add per-domain skills here.

## Mirror to VPS

When SOUL.md or config changes, deploy via:

```bash
# From VPS (post git pull)
cp ~/benjaminos/packages/hermes/SOUL.md ~/.hermes/SOUL.md
# Restart Hermes TUI to pick up persona changes
```

A post-pull hook in `infrastructure/vps-scripts/post-pull.sh` *(planned)* will automate this.

## Architecture

Hermes is a *runtime*, not a model. It loads:
- `SOUL.md` (slot #1 of system prompt — primary identity)
- Skills from `skills/` and Hermes' built-in library
- MCP servers configured in `~/.hermes/config.yaml` (currently: gbrain, linear)

Pharoah-the-CoS persona + Hermes-the-runtime = "Pharoah-on-Telegram."

See `Shared drives/BenjaminOS/1-Projects/PharoahOS/hermes-tools-rollout-plan.md` for the live wiring plan.
