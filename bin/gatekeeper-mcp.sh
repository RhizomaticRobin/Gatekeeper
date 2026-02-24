#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
SERVER="$PLUGIN_ROOT/gatekeeper-mcp/src/gatekeeper_mcp/__main__.py"

# Install dependencies if needed
if ! python3 -c "import fastmcp" 2>/dev/null; then
  pip install fastmcp >&2
fi

exec python3 -m gatekeeper_mcp
