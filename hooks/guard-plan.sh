#!/bin/bash

# Guard Plan Hook (PreToolUse: Write|Edit) — Gatekeeper
#
# Protects plan.yaml and task prompt files from modification during execution.
# Active when .claude/plan-locked exists (created by /cross-team setup).
#
# Protected files:
#   - .claude/plan/plan.yaml
#   - .claude/plan/tasks/*
#
# The orchestrator marks tasks complete via plan_utils.py (Bash tool),
# which does not trigger Write|Edit hooks.

INPUT=$(cat)

# Only guard when plan is locked
if [[ ! -f ".claude/plan-locked" ]]; then
  exit 0
fi

TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
if [[ -z "$TOOL" ]]; then
  exit 0
fi

# Extract file path from Write or Edit tool input
FILEPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
if [[ -z "$FILEPATH" ]]; then
  exit 0
fi

# Block modifications to plan files
case "$FILEPATH" in
  */.claude/plan/plan.yaml|*plan/plan.yaml)
    echo "BLOCKED: plan.yaml is locked during execution." >&2
    exit 2
    ;;
  */.claude/plan/tasks/*)
    echo "BLOCKED: Task prompt files are locked during execution." >&2
    exit 2
    ;;
esac

exit 0
