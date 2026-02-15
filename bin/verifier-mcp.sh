#!/bin/bash
# Verifier MCP server launcher
# Auto-builds verifier-mcp on first run, then starts the server.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_DIR="$PLUGIN_ROOT/verifier-mcp"
MCP_ENTRY="$MCP_DIR/dist/index.js"

# Verify source exists (bundled with plugin, not cloned)
if [[ ! -f "$MCP_DIR/package.json" ]]; then
  echo "verifier-mcp: ERROR — source not found at $MCP_DIR" >&2
  exit 1
fi

# Install dependencies if needed
if [[ ! -d "$MCP_DIR/node_modules" ]]; then
  echo "verifier-mcp: Installing dependencies..." >&2
  (cd "$MCP_DIR" && npm install --production=false) >&2
fi

# Build if needed
if [[ ! -f "$MCP_ENTRY" ]]; then
  echo "verifier-mcp: Building..." >&2
  (cd "$MCP_DIR" && npm run build) >&2
fi

# Start the server
exec node "$MCP_ENTRY" "$@"
