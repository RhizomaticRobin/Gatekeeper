#!/usr/bin/env bash
# Shared logging helper for GSD-VGL shell scripts.
#
# Usage:
#   source "${PLUGIN_ROOT}/scripts/gk_log.sh"   (or source by relative path)
#   gk_error "Something went wrong"
#   gk_warn "Non-fatal issue"
#   gk_info "Informational message"
#
# All messages go to BOTH stderr AND the log file.
# Log file: ${GATEKEEPER_LOG:-.claude/gatekeeper.log}
# Format: [ISO8601] [LEVEL] [script:line] message

GATEKEEPER_LOG="${GATEKEEPER_LOG:-.claude/gatekeeper.log}"
_GK_LOG_SCRIPT="$(basename "${BASH_SOURCE[1]:-${0:-unknown}}")"

_gk_log() {
  local level="$1"; shift
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date +%s)"
  local caller_line="${BASH_LINENO[1]:-0}"
  local msg="[$ts] [$level] [${_GK_LOG_SCRIPT}:${caller_line}] $*"
  echo "$msg" >&2
  mkdir -p "$(dirname "$GATEKEEPER_LOG")" 2>/dev/null
  echo "$msg" >> "$GATEKEEPER_LOG" 2>/dev/null
}

gk_error() { _gk_log "ERROR" "$@"; }
gk_warn()  { _gk_log "WARN"  "$@"; }
gk_info()  { _gk_log "INFO"  "$@"; }
