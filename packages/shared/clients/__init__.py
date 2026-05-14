"""Shared HTTP/API clients used across BenjaminOS packages.

Each client is a thin wrapper around the underlying SDK or HTTP API:
- supabase: read/write to Pharoah Supabase schema
- linear: create/update Linear issues via the API
- clickup: create tasks in ClickUp lists
- anthropic: classifier LLM calls (used by pharoah.classifier)

Clients read credentials from environment variables (or Infisical when wired).
Each client raises a clear error if its credentials are missing — fail fast.

These are SKELETONS for the BEN-51 PR. Real implementations land in BEN-76.
"""
