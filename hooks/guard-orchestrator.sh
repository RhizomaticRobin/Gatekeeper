#!/bin/bash

# Guard Orchestrator Hook (PreToolUse: Write|Edit|WebFetch|WebSearch) — Gatekeeper
#
# When team mode is active (.claude/gk-team-active exists), the main session
# is the Lead Orchestrator. The orchestrator coordinates workers — it does NOT
# write code or modify source files.
#
# Blocked tools during team orchestration:
#   - Write, Edit       (orchestrator must not modify source files)
#   - WebFetch, WebSearch (orchestrator has no web access)
#
# Allowed tools (not matched by this hook):
#   - Read, Task, Bash   (needed for plan management and spawning workers)

INPUT=$(cat)

# Only guard when team mode is active
TEAM_MARKER=".claude/gk-team-active"
if [[ ! -f "$TEAM_MARKER" ]]; then
  exit 0
fi

# Extract the tool name
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

if [[ -z "$TOOL" ]]; then
  exit 0
fi

echo "BLOCKED: $TOOL is not available during team orchestration." >&2
echo "You are the Lead Orchestrator — you coordinate workers, you do NOT write code." >&2
echo "Use Task(subagent_type='executor') to spawn workers for implementation." >&2
exit 2
