#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
SERVER="$PLUGIN_ROOT/evolve-mcp/server.py"

if ! python3 -c "import fastmcp" 2>/dev/null; then
  pip install fastmcp >&2
fi

exec python3 "$SERVER"
