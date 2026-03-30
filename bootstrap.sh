#!/usr/bin/env bash
# Convenience wrapper — runs the bootstrap installer from the repo root.
exec "$(dirname "$0")/scripts/bootstrap.sh" "$@"
