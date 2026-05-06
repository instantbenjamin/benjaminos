# packages/ingest

Capture sync scripts. Pull data from external sources into BenjaminOS storage layers (Wiki + GBrain + Supabase + Linear).

## Current scripts

- `raindrop_sync.py` — Raindrop bookmarks → Wiki (Tier 1/2/3 logic, collection mirror)
- `readwise_sync.py` — Readwise highlights/docs → Wiki
- `workflowy_opml_to_md.py` — Workflowy OPML export → Wiki markdown (PARA deep-split)
- `voicenotes_processor.py` *(planned, BEN-51)* — Watch `~/wiki/raw/personal/voicenotes/`, classify, route

## Conventions

- Each script is idempotent — re-runs are safe
- Dedupe by `source_id` glob in target directory
- Secrets via Infisical CLI: `infisical run --env=dev -- python -m ingest.raindrop_sync`
- Tests under `tests/ingest/`

## Run patterns

```bash
# One-off
python -m ingest.raindrop_sync

# Scheduled (Cowork scheduled task or VPS cron — both work)
infisical run --env=dev -- python -m ingest.raindrop_sync
```
