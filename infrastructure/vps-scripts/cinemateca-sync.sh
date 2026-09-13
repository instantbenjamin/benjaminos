#!/usr/bin/env bash
set -euo pipefail
: "${BENJAMINOS_ROOT:?Set the BenjaminOS checkout path}"
: "${CINEMATECA_CONFIG:?Set the private Cinemateca config path}"
# Configure named Infisical retrieval in the private config; never echo environment.
exec "${BENJAMINOS_ROOT}/.venv/bin/movie-calendar" run \
  --config "${CINEMATECA_CONFIG}" --trakt --google --apply
