#!/bin/bash

# Transition Task Script (GSD-VGL)
# Called by stop hook on PASS when plan file exists.
#
# 1. Reads current task_id from state file
# 2. Marks it completed in plan.yaml
# 3. Finds next unblocked task
# 4. Outputs transition info
#
# Exit codes:
#   0 = next task found (JSON on stdout)
#   2 = all tasks complete (no next task)
#   1 = error

set -euo pipefail

PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
SCRIPTS_DIR="${PLUGIN_ROOT}/scripts"
PLAN_FILE=".claude/plan/plan.yaml"
STATE_FILE=".claude/verifier-loop.local.md"

# Check plan file
if [[ ! -f "$PLAN_FILE" ]]; then
  echo "Error: Plan file not found: $PLAN_FILE" >&2
  exit 1
fi

# Read current task_id from state file frontmatter
if [[ ! -f "$STATE_FILE" ]]; then
  echo "Error: State file not found: $STATE_FILE" >&2
  exit 1
fi

FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$STATE_FILE")
CURRENT_TASK_ID=$(echo "$FRONTMATTER" | grep '^task_id:' | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/')

if [[ -z "$CURRENT_TASK_ID" ]]; then
  echo "Error: No task_id in state file frontmatter" >&2
  exit 1
fi

# Mark current task as completed
echo "Completing task: $CURRENT_TASK_ID" >&2
python3 "${SCRIPTS_DIR}/plan_utils.py" "$PLAN_FILE" --complete-task "$CURRENT_TASK_ID" >/dev/null

# Find next task
NEXT_JSON=$(python3 "${SCRIPTS_DIR}/next-task.py" "$PLAN_FILE")

if [[ "$NEXT_JSON" == "null" ]]; then
  echo "All plan tasks complete" >&2
  exit 2
fi

NEXT_ID=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
NEXT_NAME=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
echo "Next task: $NEXT_ID - $NEXT_NAME" >&2

# Output next task JSON to stdout
echo "$NEXT_JSON"
exit 0
