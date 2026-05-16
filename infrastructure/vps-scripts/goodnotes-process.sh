#!/bin/bash
set -e
set -a; source "$HOME/.pharoah/.env"; set +a
export PATH="$HOME/.bun/bin:$PATH"
cd "$HOME/benjaminos"
exec python3 -u packages/ingest/goodnotes_processor.py
