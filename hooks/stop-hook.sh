#!/bin/bash

# Gatekeeper Stop Hook
#
# In team mode (.claude/gk-team-active exists), the orchestrator manages all
# lifecycle — token validation, task transitions, resilience. The stop hook
# simply exits to let the orchestrator handle everything.
#
# If no team mode is active and no verifier loop state exists, exit cleanly.

set -euo pipefail

PLUGIN_ROOT_LOG="$(dirname "$(dirname "$(realpath "$0")")")"
source "${PLUGIN_ROOT_LOG}/scripts/gk_log.sh"

DEBUG_LOG="/tmp/gatekeeper-stop-hook.debug.log"
debug() {
  echo "[$(date +%H:%M:%S)] $*" >> "$DEBUG_LOG" 2>/dev/null || true
}
debug "=== STOP HOOK FIRED ==="

# Read hook input from stdin (required by hook protocol)
HOOK_INPUT=$(cat)

# Team mode: orchestrator handles lifecycle
if [[ -f ".claude/gk-team-active" ]]; then
  debug "TEAM MODE ACTIVE — skipping Gatekeeper processing"
  exit 0
fi

# No team mode, no verifier loop — clean exit
debug "NO TEAM MODE — passthrough"
exit 0
