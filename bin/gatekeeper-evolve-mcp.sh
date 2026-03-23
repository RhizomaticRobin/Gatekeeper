#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_SRC="$PLUGIN_ROOT/gatekeeper-evolve-mcp/src"

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

if ! "$PYTHON" -c "import jinja2" 2>/dev/null; then
  echo "💨 LOUD WET FART: jinja2 not installed for $PYTHON" >&2
  "$PYTHON" -m pip install --break-system-packages jinja2 >&2 || {
    echo "💨 LOUD WET FART: pip install jinja2 FAILED" >&2
    exit 1
  }
fi

if ! "$PYTHON" -c "import z3" 2>/dev/null; then
  echo "💨 LOUD WET FART: z3-solver not installed for $PYTHON" >&2
  "$PYTHON" -m pip install --break-system-packages z3-solver >&2 || {
    echo "💨 LOUD WET FART: pip install z3-solver FAILED" >&2
    exit 1
  }
fi

export PYTHONPATH="${MCP_SRC}${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" "$MCP_SRC/gatekeeper_evolve_mcp/__main__.py"
