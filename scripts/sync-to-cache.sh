#!/usr/bin/env bash
set -euo pipefail

# Sync Gatekeeper source to Claude Code plugin cache.
#
# Usage:
#   scripts/sync-to-cache.sh [options]
#
# Options:
#   --rebuild-hooks         Force rebuild hooks before sync
#   --dry-run               Show what would be synced without doing it
#   --config-dir <path>     Custom Claude config directory
#   -h, --help              Show help

RED='\033[38;2;220;20;60m'
GREEN='\033[32m'
YELLOW='\033[33m'
DIM='\033[2m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
REBUILD_HOOKS=false
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild-hooks) REBUILD_HOOKS=true; shift ;;
    --dry-run)       DRY_RUN=true; shift ;;
    --config-dir)    CLAUDE_DIR="$2"; shift 2 ;;
    -h|--help)
      sed -n '3,13p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo -e "${RED}Unknown option: $1${RESET}" >&2; exit 1 ;;
  esac
done

# Check prerequisites
for cmd in jq rsync; do
  if ! command -v "$cmd" &>/dev/null; then
    echo -e "${RED}Required command not found: $cmd${RESET}" >&2
    exit 1
  fi
done

# Resolve cache path from installed_plugins.json
PLUGINS_JSON="${CLAUDE_DIR}/plugins/installed_plugins.json"
if [[ ! -f "$PLUGINS_JSON" ]]; then
  echo -e "${YELLOW}No installed_plugins.json found — plugin not installed to cache.${RESET}"
  echo "Run: claude plugin install gatekeeper"
  exit 0
fi

CACHE_DIR=$(jq -r '.plugins["gatekeeper@gatekeeper"][0].installPath // empty' "$PLUGINS_JSON")
if [[ -z "$CACHE_DIR" ]]; then
  echo -e "${YELLOW}Gatekeeper not found in installed plugins.${RESET}"
  echo "Run: claude plugin install gatekeeper"
  exit 0
fi

if [[ ! -d "$CACHE_DIR" ]]; then
  echo -e "${YELLOW}Cache directory does not exist: ${CACHE_DIR}${RESET}"
  echo "Run: claude plugin install gatekeeper"
  exit 0
fi

echo -e "${DIM}Source:${RESET} $SOURCE_DIR"
echo -e "${DIM}Cache:${RESET}  $CACHE_DIR"

# Rebuild hooks if source changed or forced
SRC_HASH=$(md5sum "${SOURCE_DIR}/scripts/build-hooks.js" 2>/dev/null | cut -d' ' -f1 || true)
CACHE_HASH=$(md5sum "${CACHE_DIR}/scripts/build-hooks.js" 2>/dev/null | cut -d' ' -f1 || true)
if [[ "$REBUILD_HOOKS" == "true" ]] || [[ "$SRC_HASH" != "$CACHE_HASH" ]]; then
  echo -e "${YELLOW}Rebuilding hooks...${RESET}"
  (cd "$SOURCE_DIR" && npm run build:hooks 2>&1) || echo -e "${YELLOW}Hook rebuild failed (non-fatal)${RESET}"
fi

# Excludes matching install-lib.js EXCLUDE set + Better-OpenCodeMCP
RSYNC_FLAGS=(-rlptv --delete
  --exclude='node_modules'
  --exclude='.git'
  --exclude='.github'
  --exclude='.npmrc'
  --exclude='.npmignore'
  --exclude='.gitignore'
  --exclude='.gitmodules'
  --exclude='.DS_Store'
  --exclude='.claude'
  --exclude='.planning'
  --exclude='tests'
  --exclude='vitest.config.js'
  --exclude='pytest.ini'
  --exclude='package-lock.json'
  --exclude='Better-OpenCodeMCP'
)

if [[ "$DRY_RUN" == "true" ]]; then
  RSYNC_FLAGS+=(-n)
  echo -e "${YELLOW}Dry run — no files will be modified${RESET}"
fi

START=$(date +%s)
SYNC_OUTPUT=$(rsync "${RSYNC_FLAGS[@]}" "${SOURCE_DIR}/" "${CACHE_DIR}/" 2>&1)

# Sync Better-OpenCodeMCP dist/ separately (excluded above due to node_modules size)
if [[ -d "${SOURCE_DIR}/Better-OpenCodeMCP/dist" ]]; then
  OPENCODE_SYNC=$(rsync -rlptv --delete \
    "${SOURCE_DIR}/Better-OpenCodeMCP/dist/" \
    "${CACHE_DIR}/Better-OpenCodeMCP/dist/" 2>&1)
  SYNC_OUTPUT="${SYNC_OUTPUT}
${OPENCODE_SYNC}"
fi

END=$(date +%s)

# Make scripts executable in cache
if [[ "$DRY_RUN" == "false" ]]; then
  command find "${CACHE_DIR}" -name "*.sh" -exec chmod +x {} + 2>/dev/null || true
  command find "${CACHE_DIR}/hooks" -name "*.js" -exec chmod +x {} + 2>/dev/null || true
fi

# Summary
FILE_COUNT=$(echo "$SYNC_OUTPUT" | grep -c '^[^.]' || true)
ELAPSED=$((END - START))

echo "$SYNC_OUTPUT"
echo ""
echo -e "${GREEN}Sync complete${RESET} — ${FILE_COUNT} items transferred in ${ELAPSED}s"
