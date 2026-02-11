#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ROOT="${1:?Usage: cross-team-setup.sh <plugin_root>}"
PLAN_FILE=".claude/plan/plan.yaml"
CROSS_ERROR=""

# 1. Check plan file exists
if [[ ! -f "$PLAN_FILE" ]]; then
  CROSS_ERROR="PLAN_NOT_FOUND: Plan file not found at $PLAN_FILE"
  echo "$CROSS_ERROR"
  echo "Expected location: .claude/plan/plan.yaml (relative to project root)"
  echo "Current directory: $(pwd)"
  ls -la .claude/plan/ 2>/dev/null || echo ".claude/plan/ directory does not exist"
  echo "CROSS_TEAM_FAILED"
  exit 0
fi

# 2. Validate plan
echo "Validating plan..."
VALIDATE_EXIT=0
VALIDATE_OUTPUT=$(python3 "${PLUGIN_ROOT}/scripts/validate-plan.py" "$PLAN_FILE" 2>&1) || VALIDATE_EXIT=$?
echo "$VALIDATE_OUTPUT"
if [[ $VALIDATE_EXIT -ne 0 ]]; then
  CROSS_ERROR="VALIDATION_FAILED: plan.yaml has errors"
  echo "$CROSS_ERROR"
  echo "CROSS_TEAM_FAILED"
  exit 0
fi

# 3. Find ALL unblocked tasks
echo ""
echo "Finding all unblocked tasks..."
UNBLOCKED_JSON=$(python3 "${PLUGIN_ROOT}/scripts/get-unblocked-tasks.py" "$PLAN_FILE" 2>&1) || true

TASK_COUNT=$(echo "$UNBLOCKED_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null) || TASK_COUNT="0"

if [[ "$TASK_COUNT" == "0" ]]; then
  ALL_COMPLETE=$(python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan
plan = load_plan('$PLAN_FILE')
all_tasks = []
for phase in plan.get('phases', []):
    all_tasks.extend(phase.get('tasks', []))
pending = [t for t in all_tasks if t.get('status') != 'completed']
print('yes' if not pending else 'no')
" 2>/dev/null) || ALL_COMPLETE="no"

  if [[ "$ALL_COMPLETE" == "yes" ]]; then
    echo "ALL PLAN TASKS COMPLETE — nothing to do."
    echo "CROSS_TEAM_COMPLETE"
  else
    echo "No unblocked tasks available (some tasks may be in_progress or blocked)."
    echo "CROSS_TEAM_BLOCKED"
  fi
  exit 0
fi

echo "Found $TASK_COUNT unblocked task(s)"

# 4. If only 1 unblocked task, fall through to single-task execution
if [[ "$TASK_COUNT" == "1" ]]; then
  SINGLE_TASK_ID=$(echo "$UNBLOCKED_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])" 2>/dev/null)
  SINGLE_TASK_NAME=$(echo "$UNBLOCKED_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['name'])" 2>/dev/null)
  echo ""
  echo "1 unblocked task: $SINGLE_TASK_ID - $SINGLE_TASK_NAME"
  echo "Running in single-task mode."
  echo "SINGLE_TASK_ID=$SINGLE_TASK_ID"
  echo "CROSS_TEAM_SINGLE_OK"
  exit 0
fi

# 5. Extract task IDs and check file scope conflicts
TASK_IDS=$(echo "$UNBLOCKED_JSON" | python3 -c "
import sys, json
tasks = json.load(sys.stdin)
print(' '.join(t['id'] for t in tasks))
" 2>/dev/null) || true

echo ""
echo "Checking file scope conflicts..."
CONFLICT_JSON=$(python3 "${PLUGIN_ROOT}/scripts/check-file-conflicts.py" "$PLAN_FILE" $TASK_IDS 2>&1) || true
echo "$CONFLICT_JSON"

SAFE_COUNT=$(echo "$CONFLICT_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['safe_parallel']))" 2>/dev/null) || SAFE_COUNT="0"
SEQ_COUNT=$(echo "$CONFLICT_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['sequential_fallback']))" 2>/dev/null) || SEQ_COUNT="0"

echo ""
echo "Safe to parallelize: $SAFE_COUNT task(s)"
echo "Sequential fallback: $SEQ_COUNT task(s)"

# 6. Create team state
mkdir -p .claude/vgl-sessions
date -u +%Y-%m-%dT%H:%M:%SZ > .claude/vgl-team-active

# 7. Set up per-task VGL sessions for parallelizable tasks
DISPATCH_TASKS=""
SESSION_DIR_LIST=""

SAFE_IDS=$(echo "$CONFLICT_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
safe = data['safe_parallel']
seq = data['sequential_fallback']
conflicts = data['conflicts']
if not safe and not conflicts:
    print(' '.join(seq))
else:
    print(' '.join(safe))
" 2>/dev/null) || true

if [[ -z "$SAFE_IDS" ]]; then
  echo "No tasks can be safely parallelized. Falling back to sequential execution."
  # Use all task IDs for sequential execution
  SAFE_IDS="$TASK_IDS"
  SAFE_COUNT="$TASK_COUNT"
fi

for TASK_ID in $SAFE_IDS; do
  SESSION_DIR=".claude/vgl-sessions/task-${TASK_ID}"
  mkdir -p "$SESSION_DIR"

  TASK_JSON=$(python3 -c "
import sys, json
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan, find_task
plan = load_plan('$PLAN_FILE')
_, task = find_task(plan, '$TASK_ID')
print(json.dumps(task))
" 2>/dev/null) || continue

  TASK_NAME=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))" 2>/dev/null) || true
  TEST_CMD=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['tests']['quantitative']['command'])" 2>/dev/null) || true
  PROMPT_FILE=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['prompt_file'])" 2>/dev/null) || true
  QUAL_CRITERIA=$(echo "$TASK_JSON" | python3 -c "
import sys, json
t = json.load(sys.stdin)
criteria = t.get('tests', {}).get('qualitative', {}).get('criteria', [])
for c in criteria:
    print(f'- {c}')
" 2>/dev/null) || true

  FULL_PROMPT_PATH=".claude/plan/${PROMPT_FILE}"
  if [[ -n "$PROMPT_FILE" ]] && [[ -f "$FULL_PROMPT_PATH" ]]; then
    TASK_PROMPT=$(cat "$FULL_PROMPT_PATH")
  else
    TASK_PROMPT="Implement task $TASK_ID: $TASK_NAME"
  fi

  RAW_TASK_PROMPT="$TASK_PROMPT"

  TASK_PROMPT="CRITICAL RULES — VIOLATION WILL BREAK THE LOOP:
- Do NOT modify .claude/plan/plan.yaml or any .claude/ state files
- Do NOT mark tasks as done or completed — the lead agent handles all transitions
- Do NOT edit .claude/verifier-loop.local.md or .claude/verifier-token.secret

YOUR TASK:
$TASK_PROMPT"

  # Mark task as in_progress
  python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan, save_plan
plan = load_plan('$PLAN_FILE')
for phase in plan.get('phases', []):
    for task in phase.get('tasks', []):
        if str(task['id']) == '$TASK_ID':
            task['status'] = 'in_progress'
save_plan('$PLAN_FILE', plan)
" 2>/dev/null || true

  export _VGL_TASK_PROMPT="$TASK_PROMPT"
  export _VGL_RAW_TASK_PROMPT="$RAW_TASK_PROMPT"
  export _VGL_TEST_CMD="$TEST_CMD"
  export _VGL_QUAL_CRITERIA="$QUAL_CRITERIA"
  export _VGL_TASK_ID="$TASK_ID"
  export _VGL_TASK_JSON="$TASK_JSON"
  export _VGL_SESSION_DIR="$SESSION_DIR"
  SETUP_JSON=$(python3 << 'PYEOF'
import json, os
print(json.dumps({
    "prompt": os.environ["_VGL_TASK_PROMPT"],
    "verification_criteria": "Quantitative: {} must pass\nQualitative:\n{}".format(
        os.environ["_VGL_TEST_CMD"], os.environ["_VGL_QUAL_CRITERIA"]),
    "test_command": os.environ["_VGL_TEST_CMD"],
    "verifier_model": "opus",
    "max_iterations": 0,
    "plan_mode": True,
    "task_id": os.environ["_VGL_TASK_ID"],
    "task_json": os.environ["_VGL_TASK_JSON"],
    "task_prompt_content": os.environ["_VGL_RAW_TASK_PROMPT"],
    "session_dir": os.environ["_VGL_SESSION_DIR"],
}))
PYEOF
  ) || continue

  "${PLUGIN_ROOT}/scripts/setup-verifier-loop.sh" --from-json "$SETUP_JSON" 2>&1 || {
    echo "WARNING: Failed to set up VGL for task $TASK_ID"
    continue
  }

  DISPATCH_TASKS="${DISPATCH_TASKS}
- Task $TASK_ID ($TASK_NAME): session_dir=$SESSION_DIR"
  SESSION_DIR_LIST="${SESSION_DIR_LIST}
  task-${TASK_ID} -> $SESSION_DIR"
done

echo ""
echo "==============================================================================="
echo "              TEAM MODE ACTIVATED — $SAFE_COUNT parallel tasks"
echo "==============================================================================="
echo ""
echo "Tasks dispatched:$DISPATCH_TASKS"
echo ""
echo "Session directories:$SESSION_DIR_LIST"
echo ""
echo "Team marker: .claude/vgl-team-active"
echo ""
echo "CROSS_TEAM_OK"
