#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_SRC="$PLUGIN_ROOT/gatekeeper-evolve-mcp/src"

# Install dependencies if needed
if ! python3 -c "import fastmcp" 2>/dev/null; then
  pip install fastmcp >&2
fi

if ! python3 -c "import jinja2" 2>/dev/null; then
  pip install jinja2 >&2
fi

if ! python3 -c "import z3" 2>/dev/null; then
  pip install z3-solver >&2
fi

export PYTHONPATH="${MCP_SRC}${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$MCP_SRC/gatekeeper_evolve_mcp/__main__.py"
