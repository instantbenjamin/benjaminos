# infrastructure

VPS-side scripts and cron specs. The "where the code actually runs" layer.

## Subdirectories

- `vps-scripts/` — Bash wrappers run on the VPS (wiki-sync, gbrain-import, gbrain-embed, etc.). Replaces the old `~/bin/` pattern with version-controlled equivalents.
- `cron/` — Cron specs as code. Source of truth for what's scheduled where.

## Deploy pattern

The VPS clones this repo to `~/benjaminos/`. A `git pull` cron keeps it current.

```bash
# On VPS
cd ~/benjaminos && git pull
# Optional: trigger any post-pull hooks (mirror SOUL.md, regenerate cron entries, etc.)
infrastructure/vps-scripts/post-pull.sh
```

Existing VPS scripts at `~/bin/` are migrated here; symlinks back to `~/bin/` keep existing cron jobs working during the transition.

## Conventions

- Bash scripts use `#!/usr/bin/env bash` + `set -euo pipefail`
- Secrets fetched via `infisical run` rather than read from env files
- Scripts log to stderr; cron captures via journald or shell redirect
- Each script's purpose documented in a top-of-file comment
