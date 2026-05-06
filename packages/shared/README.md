# packages/shared

Cross-package utilities. Clients for the four shared substrates:

- `supabase.py` — typed wrapper around `supabase-py`, pulls `SUPABASE_DATABASE_URL` from env
- `gbrain.py` — wraps `gbrain` CLI / MCP for typed Python access (planned)
- `linear.py` — Linear API client wrapper (planned)
- `infisical.py` — secret retrieval via `infisical run` and `infisical secrets get`

Plus generic helpers:

- `paths.py` — known paths (Drive locations, VPS paths, wiki root) as constants
- `logging.py` — consistent JSON logging across all packages

## Conventions

- One module per external service
- All clients lazy-init (don't connect at import time)
- All functions return typed Pydantic models, not dicts
