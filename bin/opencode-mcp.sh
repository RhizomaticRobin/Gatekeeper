#!/bin/bash
# Opencode MCP server launcher
# Auto-builds Better-OpenCodeMCP on first run, then starts the server.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_DIR="$PLUGIN_ROOT/Better-OpenCodeMCP"
MCP_ENTRY="$MCP_DIR/dist/index.js"
REPO_URL="https://github.com/RhizomaticRobin/Better-OpenCodeMCP.git"

# If submodule directory is empty or missing, clone it
if [[ ! -f "$MCP_DIR/package.json" ]]; then
  echo "opencode-mcp: Cloning MCP server..." >&2
  if [[ -d "$MCP_DIR" ]]; then
    rm -rf "$MCP_DIR"
  fi
  git clone --depth 1 "$REPO_URL" "$MCP_DIR" >&2
fi

# Install dependencies if needed
if [[ ! -d "$MCP_DIR/node_modules" ]]; then
  echo "opencode-mcp: Installing dependencies..." >&2
  (cd "$MCP_DIR" && npm install --production=false) >&2
fi

# Build if needed
if [[ ! -f "$MCP_ENTRY" ]]; then
  echo "opencode-mcp: Building..." >&2
  (cd "$MCP_DIR" && npm run build) >&2
fi

# Resolve model from opencode template if no config exists
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode-mcp"
if [[ ! -f "$CONFIG_DIR/config.json" ]]; then
  TEMPLATE="$PLUGIN_ROOT/templates/opencode.json"
  if [[ -f "$TEMPLATE" ]]; then
    MODEL=$(python3 -c "import json,sys; t=json.load(open('$TEMPLATE')); print(t.get('agent',{}).get('gk-builder',{}).get('model',''))" 2>/dev/null || true)
    if [[ -n "$MODEL" ]]; then
      mkdir -p "$CONFIG_DIR"
      echo "{\"model\": \"$MODEL\"}" > "$CONFIG_DIR/config.json"
      echo "opencode-mcp: Auto-configured model=$MODEL from template" >&2
    fi
  fi
fi

# Start the server
exec node "$MCP_ENTRY" "$@"
