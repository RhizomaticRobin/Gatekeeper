#!/bin/bash

# Guard Skills Hook (PreToolUse: Skill) — Gatekeeper
#
# When a Gatekeeper loop is active, block all gatekeeper skills except /cross-team.
# This prevents the agent from:
#   - Running /quest (would overwrite the plan mid-execution)
#   - Running /bridge (would start a competing non-plan loop)
#   - Running /run-away (only the user should cancel)
#   - Running /help (unnecessary noise during loop)
#
# /cross-team is allowed because the auto-transition stop hook uses it
# and the agent may need to re-enter after a failure.

INPUT=$(cat)

# Extract the skill name from the tool input
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null)

# If no skill name, allow (not a skill call we care about)
if [[ -z "$SKILL" ]]; then
  exit 0
fi

# Only guard when a Gatekeeper loop is active
STATE_FILE=".claude/verifier-loop.local.md"
if [[ ! -f "$STATE_FILE" ]]; then
  exit 0
fi

# Normalize skill name — strip "gatekeeper:" prefix if present
BARE_SKILL="${SKILL#gatekeeper:}"

# Allow /cross-team through — needed for auto-transition and recovery
if [[ "$BARE_SKILL" == "cross-team" ]]; then
  exit 0
fi

# Allow /progress through — useful for status checks during loop
if [[ "$BARE_SKILL" == "progress" ]]; then
  exit 0
fi

# Block all other gatekeeper skills during active Gatekeeper loop
case "$BARE_SKILL" in
    quest|new-project|bridge|run-away|research|map-codebase|settings|verify-milestone|debug|help)
    echo "BLOCKED: /$SKILL is not available during an active Gatekeeper loop." >&2
    echo "The Gatekeeper loop is running — focus on the current task." >&2
    echo "Only /cross-team and /progress are allowed. To cancel, the USER must run /run-away." >&2
    exit 2
    ;;
esac

# Not a gatekeeper skill — allow it
exit 0
