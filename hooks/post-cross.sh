#!/bin/bash

# Post-Cross Hook (PostToolUse: Skill) — GSD-VGL
#
# After /cross-team completes successfully, show the agent the next task
# in the pipeline (the one AFTER the task that was just launched).

INPUT=$(cat)

# Extract skill name
SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null)

# Normalize — strip prefix
BARE_SKILL="${SKILL#gatekeeper:}"

# Only act on /cross or /cross-team
if [[ "$BARE_SKILL" != "cross" ]] && [[ "$BARE_SKILL" != "cross-team" ]]; then
  exit 0
fi

# Only if VGL is now active (cross succeeded)
STATE_FILE=".claude/verifier-loop.local.md"
if [[ ! -f "$STATE_FILE" ]]; then
  exit 0
fi

PLAN_FILE=".claude/plan/plan.yaml"
if [[ ! -f "$PLAN_FILE" ]]; then
  exit 0
fi

# Read current task ID from state file
FRONTMATTER=$(awk 'NR==1 && /^---$/{next} /^---$/{exit} NR>1{print}' "$STATE_FILE")
CURRENT_TASK_ID=$(echo "$FRONTMATTER" | grep '^task_id:' | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/')

if [[ -z "$CURRENT_TASK_ID" ]]; then
  exit 0
fi

PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
PIPELINE_INFO=$(python3 -c "
import sys, json
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan

plan = load_plan('$PLAN_FILE')

all_tasks = []
for phase in plan.get('phases', []):
    for task in phase.get('tasks', []):
        all_tasks.append(task)

total = len(all_tasks)
completed = sum(1 for t in all_tasks if t.get('status') == 'completed')
remaining = total - completed

current_idx = None
for i, t in enumerate(all_tasks):
    if str(t['id']) == '$CURRENT_TASK_ID':
        current_idx = i
        break

if current_idx is None:
    sys.exit(0)

current = all_tasks[current_idx]

next_up = None
for t in all_tasks[current_idx + 1:]:
    if t.get('status') in ('pending', None):
        next_up = t
        break

result = {
    'current_id': str(current['id']),
    'current_name': current.get('name', ''),
    'total': total,
    'completed': completed,
    'remaining': remaining,
}

if next_up:
    result['next_id'] = str(next_up['id'])
    result['next_name'] = next_up.get('name', '')
    deps = [str(d) for d in next_up.get('depends_on', [])]
    result['next_depends_on'] = deps

print(json.dumps(result))
" 2>/dev/null) || exit 0

if [[ -z "$PIPELINE_INFO" ]]; then
  exit 0
fi

CURRENT_ID=$(echo "$PIPELINE_INFO" | jq -r '.current_id')
CURRENT_NAME=$(echo "$PIPELINE_INFO" | jq -r '.current_name')
TOTAL=$(echo "$PIPELINE_INFO" | jq -r '.total')
COMPLETED=$(echo "$PIPELINE_INFO" | jq -r '.completed')
REMAINING=$(echo "$PIPELINE_INFO" | jq -r '.remaining')
NEXT_ID=$(echo "$PIPELINE_INFO" | jq -r '.next_id // empty')
NEXT_NAME=$(echo "$PIPELINE_INFO" | jq -r '.next_name // empty')

echo ""
echo "==============================================="
echo "  PLAN PROGRESS: $COMPLETED/$TOTAL completed ($REMAINING remaining)"
echo "==============================================="
echo "  NOW:  $CURRENT_ID — $CURRENT_NAME"
if [[ -n "$NEXT_ID" ]]; then
  echo "  NEXT: $NEXT_ID — $NEXT_NAME (auto-transitions on verification pass)"
else
  echo "  NEXT: None — this is the FINAL task!"
fi
echo "==============================================="
echo ""

exit 0
