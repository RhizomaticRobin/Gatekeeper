---
description: "Run away! Run away! — cancel an active Verifier-Gated Loop"
allowed-tools: ["Bash(rm:*)", "Bash(python3:*)"]
---

Check for and remove the active Verifier-Gated Loop state files:

```!
if [[ -f ".claude/verifier-loop.local.md" ]]; then
  ITERATION=$(grep '^iteration:' .claude/verifier-loop.local.md | sed 's/iteration: *//' 2>/dev/null || echo "unknown")
  SESSION_ID=$(grep '^session_id:' .claude/verifier-loop.local.md | sed 's/session_id: *//' | sed 's/^"\(.*\)"$/\1/' 2>/dev/null || echo "unknown")
  TASK_ID=$(grep '^task_id:' .claude/verifier-loop.local.md | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/' 2>/dev/null || echo "")

  rm -f .claude/verifier-loop.local.md .claude/verifier-prompt.local.md .claude/verifier-token.secret
  echo "VGL cancelled."
  echo "  Session: $SESSION_ID"
  echo "  Iteration: $ITERATION"

  if [[ -n "$TASK_ID" ]]; then
    echo "  Plan task: $TASK_ID (reverted to pending)"
    if [[ -f ".claude/plan/plan.yaml" ]]; then
      python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('${CLAUDE_PLUGIN_ROOT}/scripts'))
from plan_utils import load_plan, save_plan
plan = load_plan('.claude/plan/plan.yaml')
for phase in plan.get('phases', []):
    for task in phase.get('tasks', []):
        if str(task['id']) == '$TASK_ID' and task.get('status') == 'in_progress':
            task['status'] = 'pending'
save_plan('.claude/plan/plan.yaml', plan)
" 2>/dev/null || true
    fi
  fi

  echo ""
  echo "State files removed:"
  echo "  - .claude/verifier-loop.local.md"
  echo "  - .claude/verifier-prompt.local.md"
  echo "  - .claude/verifier-token.secret"
else
  echo "No active Verifier-Gated Loop found."
fi

# Also clean up team state if present
if [[ -f ".claude/vgl-team-active" ]]; then
  rm -f ".claude/vgl-team-active"
  rm -rf ".claude/vgl-sessions/"
  echo ""
  echo "Team mode cancelled. Team state files removed:"
  echo "  - .claude/vgl-team-active"
  echo "  - .claude/vgl-sessions/"
fi

# Unlock plan files
if [[ -f ".claude/plan-locked" ]]; then
  rm -f ".claude/plan-locked"
  echo ""
  echo "Plan unlocked — plan.yaml and task files are editable again."
fi
```

Report the cancellation status to the user.
