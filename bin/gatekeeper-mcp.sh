#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
SERVER="$PLUGIN_ROOT/gatekeeper-mcp/src/gatekeeper_mcp/__main__.py"

source "$SCRIPT_DIR/python3-resolve.sh"

# Install dependencies if needed
if ! "$PYTHON" -c "import fastmcp" 2>/dev/null; then
  echo "💨 LOUD WET FART: fastmcp not installed for $PYTHON" >&2
  echo "   Attempting auto-install..." >&2
  "$PYTHON" -m pip install --break-system-packages fastmcp >&2 || {
    echo "💨 LOUD WET FART: pip install fastmcp FAILED" >&2
    exit 1
  }
fi

exec "$PYTHON" -m gatekeeper_mcp
