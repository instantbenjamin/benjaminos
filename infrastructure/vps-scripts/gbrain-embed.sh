#!/bin/bash
set -e
set -a; source "$HOME/.gbrain/.env"; set +a
export PATH="$HOME/.bun/bin:$PATH"
exec gbrain embed --stale
