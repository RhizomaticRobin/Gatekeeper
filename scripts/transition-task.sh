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
source "${PLUGIN_ROOT}/scripts/gk_log.sh"
PLAN_FILE=".claude/plan/plan.yaml"
STATE_FILE=".claude/verifier-loop.local.md"

# Check plan file
if [[ ! -f "$PLAN_FILE" ]]; then
  echo "Error: Plan file not found: $PLAN_FILE" >&2
  echo "Try: Run /gatekeeper:quest to generate a plan, or ensure .claude/plan/plan.yaml exists." >&2
  exit 1
fi

# Read current task_id from state file frontmatter
if [[ ! -f "$STATE_FILE" ]]; then
  echo "Error: State file not found: $STATE_FILE" >&2
  echo "Try: Run /gatekeeper:cross-team to start a new VGL session." >&2
  exit 1
fi

FRONTMATTER=$(awk 'NR==1 && /^---$/{next} /^---$/{exit} NR>1{print}' "$STATE_FILE")
CURRENT_TASK_ID=$(echo "$FRONTMATTER" | grep '^task_id:' | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/') || CURRENT_TASK_ID=""

if [[ -z "$CURRENT_TASK_ID" ]]; then
  echo "Error: No task_id in state file frontmatter" >&2
  echo "Try: Check .claude/verifier-loop.local.md has a valid task_id field, or run /gatekeeper:run-away to reset." >&2
  exit 1
fi

# Extract iteration count and started_at for history recording
HISTORY_ITERATION=$(echo "$FRONTMATTER" | grep '^iteration:' | sed 's/iteration: *//' || true)
if [[ -z "$HISTORY_ITERATION" ]]; then
  gk_warn "No iteration count in state file frontmatter — defaulting to 1"
  HISTORY_ITERATION="1"
fi
HISTORY_STARTED_AT=$(echo "$FRONTMATTER" | grep '^started_at:' | sed 's/started_at: *//' | sed 's/^"\(.*\)"$/\1/' || true)
if [[ -z "$HISTORY_STARTED_AT" ]]; then
  gk_warn "No started_at in state file frontmatter — history duration will be 0"
fi
HISTORY_SESSION_ID=$(echo "$FRONTMATTER" | grep '^session_id:' | sed 's/session_id: *//' | sed 's/^"\(.*\)"$/\1/' || true)
if [[ -z "$HISTORY_SESSION_ID" ]]; then
  gk_warn "No session_id in state file frontmatter"
fi

# Acquire exclusive flock for the read-modify-write cycle
# Uses the same lock file as Python's _plan_lock (plan.yaml.lock)
LOCK_FILE="${PLAN_FILE}.lock"
exec 9>"$LOCK_FILE"
flock -x 9

# Tell child Python processes that we already hold the plan lock
# so they skip their own flock (avoiding deadlock on same lock file)
export GSD_VGL_PLAN_LOCKED=1

# Read completion token — required for completing a task
TOKEN_FILE=".claude/verifier-token.secret"
# Try task-specific session dir first, then fall back to .claude/
TASK_SESSION_DIR=".claude/vgl-sessions/task-${CURRENT_TASK_ID}"
if [[ -f "${TASK_SESSION_DIR}/verifier-token.secret" ]]; then
  TOKEN_FILE="${TASK_SESSION_DIR}/verifier-token.secret"
fi

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Error: Token file not found at $TOKEN_FILE — cannot complete task without VGL token" >&2
  exit 1
fi
COMPLETION_TOKEN=$(head -1 "$TOKEN_FILE" | tr -d '\n')

# Mark current task as completed (requires valid VGL token)
echo "Completing task: $CURRENT_TASK_ID" >&2
python3 "${SCRIPTS_DIR}/plan_utils.py" "$PLAN_FILE" --complete-task "$CURRENT_TASK_ID" --token "$COMPLETION_TOKEN" >/dev/null

# Git checkpoint: commit plan.yaml status change
create_checkpoint() {
  local task_id="$1"
  local task_name="$2"

  # Skip if not in git repo
  if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "Checkpoint: skipped (not a git repository)" >&2
    return 0
  fi

  # Stage plan.yaml and any VGL state changes
  if ! git add .claude/plan/plan.yaml 2>&1; then
    echo "Checkpoint: failed to stage plan.yaml" >&2
    return 0
  fi

  # Check if anything is staged
  if git diff --cached --quiet 2>/dev/null; then
    echo "Checkpoint: skipped (no changes to commit)" >&2
    return 0
  fi

  # Create checkpoint commit
  local commit_msg="checkpoint(task-${task_id}): ${task_name}"
  if git commit -m "$commit_msg" > /dev/null 2>&1; then
    local short_sha=$(git rev-parse --short HEAD)
    echo "Checkpoint: $short_sha (task-${task_id})" >&2
  else
    echo "Checkpoint: commit failed (non-fatal)" >&2
  fi

  return 0
}

# Get task name for checkpoint message
TASK_NAME=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS_DIR}')
from plan_utils import load_plan, find_task
plan = load_plan('$PLAN_FILE')
_, task = find_task(plan, '$CURRENT_TASK_ID')
if task: print(task.get('name', 'task $CURRENT_TASK_ID'))
else: print('task $CURRENT_TASK_ID')
" 2>&1) || {
  gk_warn "Failed to get task name for $CURRENT_TASK_ID"
  TASK_NAME="task $CURRENT_TASK_ID"
}

create_checkpoint "$CURRENT_TASK_ID" "$TASK_NAME"

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
" 2>&1) || {
  gk_warn "Failed to check integration status — assuming not needed"
  INTEGRATION_CHECK="false"
}

if [[ "$INTEGRATION_CHECK" == "true" ]]; then
  echo "INTEGRATION_CHECK_NEEDED" >&2
fi

# Find next task
NEXT_JSON=$(python3 "${SCRIPTS_DIR}/next-task.py" "$PLAN_FILE")

# Release the flock and clear the lock environment variable
flock -u 9
exec 9>&-
unset GSD_VGL_PLAN_LOCKED

# Record history (non-blocking: if run_history.py fails or is missing, transition still works)
HISTORY_DURATION=0
if [[ -n "$HISTORY_STARTED_AT" ]]; then
  STARTED_EPOCH=$(date -d "$HISTORY_STARTED_AT" +%s 2>/dev/null || date -jf "%Y-%m-%dT%H:%M:%SZ" "$HISTORY_STARTED_AT" +%s 2>/dev/null || echo "0")
  NOW_EPOCH=$(date +%s)
  if [[ "$STARTED_EPOCH" -gt 0 ]]; then
    HISTORY_DURATION=$(( NOW_EPOCH - STARTED_EPOCH ))
  fi
fi

HISTORY_ITERATIONS="${HISTORY_ITERATION:-1}"

if [[ -f "${SCRIPTS_DIR}/run_history.py" ]]; then
  if python3 "${SCRIPTS_DIR}/run_history.py" \
    --record \
    --task-id "$CURRENT_TASK_ID" \
    --iterations "$HISTORY_ITERATIONS" \
    --passed \
    --duration "$HISTORY_DURATION" \
    --session-id "${HISTORY_SESSION_ID:-}" \
    --history-dir ".planning/history" \
    2>&1; then
    echo "History recorded for task $CURRENT_TASK_ID" >&2
  else
    gk_warn "Failed to record history for task $CURRENT_TASK_ID"
  fi
else
  echo "History: run_history.py not found, skipping recording" >&2
fi

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
" 2>&1) || {
    gk_warn "Failed to inject integration check flag into next task JSON"
  }
fi

# Output next task JSON to stdout
echo "$NEXT_JSON"
exit 0
