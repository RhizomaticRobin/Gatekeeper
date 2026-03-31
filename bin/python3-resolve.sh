#!/bin/bash
# Resolve a working python3 interpreter and export it as $PYTHON.
# Sourced by MCP launchers and hook scripts.

if [[ -n "${PYTHON:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

for candidate in python3 python; do
  if command -v "$candidate" &>/dev/null; then
    PYTHON="$(command -v "$candidate")"
    export PYTHON
    return 0 2>/dev/null || exit 0
  fi
done

echo "ERROR: No python3 interpreter found on PATH" >&2
exit 1
