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

# Check if completing this task finishes a phase that needs integration checking
INTEGRATION_CHECK=$(python3 -c "
import sys, json
sys.path.insert(0, '${SCRIPTS_DIR}')
from plan_utils import load_plan

plan = load_plan('$PLAN_FILE')
current_phase_id = '$CURRENT_TASK_ID'.split('.')[0]

for phase in plan.get('phases', []):
    if str(phase.get('id')) == current_phase_id:
        # Check if all tasks in this phase are now completed
        tasks = phase.get('tasks', [])
        all_done = all(t.get('status') == 'completed' for t in tasks)
        needs_check = phase.get('integration_check', False)
        if all_done and needs_check:
            print('true')
        else:
            print('false')
        break
else:
    print('false')
" 2>/dev/null || echo "false")

if [[ "$INTEGRATION_CHECK" == "true" ]]; then
  echo "INTEGRATION_CHECK_NEEDED" >&2
fi

# Find next task
NEXT_JSON=$(python3 "${SCRIPTS_DIR}/next-task.py" "$PLAN_FILE")

if [[ "$NEXT_JSON" == "null" ]]; then
  echo "All plan tasks complete" >&2
  exit 2
fi

NEXT_ID=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
NEXT_NAME=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
echo "Next task: $NEXT_ID - $NEXT_NAME" >&2

# If integration check needed, inject it as a signal in the JSON output
if [[ "$INTEGRATION_CHECK" == "true" ]]; then
  NEXT_JSON=$(echo "$NEXT_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
task['_integration_check_before'] = True
print(json.dumps(task))
" 2>/dev/null || echo "$NEXT_JSON")
fi

# Output next task JSON to stdout
echo "$NEXT_JSON"
exit 0
