#!/bin/bash

# Guard Orchestrator Hook (PreToolUse: Write|Edit|WebFetch|WebSearch) — Gatekeeper
#
# When team mode is active (.claude/gk-team-active exists), the main session
# is the Lead Orchestrator. The orchestrator coordinates workers — it does NOT
# write code or modify source files.
#
# Detection strategy:
#   The marker file stores the orchestrator's session_id (written lazily on
#   first PreToolUse in the orchestrator's session after setup creates it).
#   Sub-agents have different session_ids and are allowed through.
#
# Blocked tools during team orchestration (orchestrator only):
#   - Write, Edit       (orchestrator must not modify source files)
#   - WebFetch, WebSearch (orchestrator has no web access)

INPUT=$(cat)

# Only guard when team mode is active
TEAM_MARKER=".claude/gk-team-active"
if [[ ! -f "$TEAM_MARKER" ]]; then
  exit 0
fi

# Extract session_id from the hook input
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
if [[ -z "$SESSION_ID" ]]; then
  # No session_id in hook input — can't distinguish, let it through
  exit 0
fi

# Read the stored orchestrator session_id
ORCH_SESSION_ID=$(cat "$TEAM_MARKER" 2>/dev/null | tr -d '[:space:]')

# Lazy init: if the marker has no session_id (just a timestamp from setup),
# the FIRST session to hit this hook is the orchestrator — stamp it.
if [[ -z "$ORCH_SESSION_ID" ]] || [[ "$ORCH_SESSION_ID" =~ ^[0-9]{4}-[0-9]{2} ]]; then
  # Marker contains a timestamp (legacy) or is empty — stamp with current session
  echo "$SESSION_ID" > "$TEAM_MARKER"
  ORCH_SESSION_ID="$SESSION_ID"
fi

# Only block the orchestrator session — sub-agents pass through
if [[ "$SESSION_ID" != "$ORCH_SESSION_ID" ]]; then
  exit 0
fi

TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
if [[ -z "$TOOL" ]]; then
  exit 0
fi

echo "BLOCKED: $TOOL is not available during team orchestration." >&2
echo "You are the Lead Orchestrator — you coordinate workers, you do NOT write code." >&2
echo "Use Task(subagent_type='executor') to spawn workers for implementation." >&2
exit 2
