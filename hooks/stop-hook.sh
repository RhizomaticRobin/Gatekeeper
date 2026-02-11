#!/bin/bash

# GSD-VGL Stop Hook
# Prevents session exit when a verifier-loop is active
# Feeds the prompt back to continue the loop until verification passes
# Enhanced with must_haves phase auto-transition and TDD+opencode signal tracking

set -euo pipefail

DEBUG_LOG="/tmp/gsd-vgl-stop-hook.debug.log"
debug() { echo "[$(date +%H:%M:%S)] $*" >> "$DEBUG_LOG" 2>/dev/null || true; }
debug "=== STOP HOOK FIRED ==="
debug "PWD=$(pwd)"

# Read hook input from stdin
HOOK_INPUT=$(cat)
debug "HOOK_INPUT_LEN=${#HOOK_INPUT}"
debug "HOOK_INPUT=$(echo "$HOOK_INPUT" | head -c 500)"

# Team mode: lead handles lifecycle, skip VGL processing
if [[ -f ".claude/vgl-team-active" ]]; then
  debug "TEAM MODE ACTIVE — skipping VGL processing"
  exit 0
fi

# Check if verifier-loop is active
STATE_FILE=".claude/verifier-loop.local.md"
TOKEN_FILE=".claude/verifier-token.secret"

if [[ ! -f "$STATE_FILE" ]]; then
  debug "NO STATE FILE — exiting"
  exit 0
fi
debug "STATE_FILE exists"

# Parse markdown frontmatter (YAML between ---) and extract values
FRONTMATTER=$(awk 'NR==1 && /^---$/{next} /^---$/{exit} NR>1{print}' "$STATE_FILE")

# Handle empty or corrupted state file (no frontmatter at all)
if [[ -z "$FRONTMATTER" ]] || ! echo "$FRONTMATTER" | grep -q '^iteration:'; then
  echo "VGL: State file corrupted or empty (no valid frontmatter). Cleaning up." >&2
  echo "  Recovery: run /gsd-vgl:run-away to reset, then restart your task." >&2
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

ITERATION=$(echo "$FRONTMATTER" | grep '^iteration:' | sed 's/iteration: *//')
MAX_ITERATIONS=$(echo "$FRONTMATTER" | grep '^max_iterations:' | sed 's/max_iterations: *//')
SESSION_ID=$(echo "$FRONTMATTER" | grep '^session_id:' | sed 's/session_id: *//' | sed 's/^"\(.*\)"$/\1/' || true)

# Handle missing session_id
if [[ -z "$SESSION_ID" ]]; then
  echo "VGL: State file corrupted (missing session_id). Cleaning up." >&2
  echo "  Recovery: run /gsd-vgl:run-away to reset, then restart your task." >&2
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

# Stale session detection: warn and cleanup if started_at > 24h ago
STARTED_AT=$(echo "$FRONTMATTER" | grep '^started_at:' | sed 's/started_at: *//' | sed 's/^"\(.*\)"$/\1/' || true)
if [[ -n "$STARTED_AT" ]]; then
  STARTED_EPOCH=$(date -d "$STARTED_AT" +%s 2>/dev/null || date -jf "%Y-%m-%dT%H:%M:%SZ" "$STARTED_AT" +%s 2>/dev/null || echo "0")
  NOW_EPOCH=$(date +%s)
  ELAPSED=$(( NOW_EPOCH - STARTED_EPOCH ))
  if [[ $STARTED_EPOCH -gt 0 ]] && [[ $ELAPSED -gt 86400 ]]; then
    HOURS_AGO=$(( ELAPSED / 3600 ))
    echo "VGL: Stale session detected (started ${HOURS_AGO}h ago, session: ${SESSION_ID}). Cleaning up." >&2
    echo "  Recovery: run /gsd-vgl:run-away to reset, then restart your task." >&2
    rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
    exit 0
  fi
fi

# Read completion token from secret file
if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "VGL: Token file not found" >&2
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi
COMPLETION_TOKEN=$(head -1 "$TOKEN_FILE" | tr -d '\n')

# Validate numeric fields
if [[ ! "$ITERATION" =~ ^[0-9]+$ ]]; then
  echo "VGL: State file corrupted (invalid iteration: '$ITERATION')" >&2
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

if [[ ! "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
  echo "VGL: State file corrupted (invalid max_iterations: '$MAX_ITERATIONS')" >&2
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

# Validate token format
if [[ ! "$COMPLETION_TOKEN" =~ ^VGL_COMPLETE_[a-f0-9]{32}$ ]]; then
  echo "VGL: Token corrupted" >&2
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

# Check max iterations
if [[ $MAX_ITERATIONS -gt 0 ]] && [[ $ITERATION -ge $MAX_ITERATIONS ]]; then
  echo "VGL: Max iterations ($MAX_ITERATIONS) reached. Session: $SESSION_ID" >&2
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

# Get transcript path from hook input (handle malformed JSON gracefully)
TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path' 2>/dev/null) || true
if [[ -z "$TRANSCRIPT_PATH" ]] || [[ "$TRANSCRIPT_PATH" == "null" ]]; then
  debug "MALFORMED OR MISSING JSON INPUT — passthrough"
  echo "VGL: Malformed hook input (could not parse transcript_path). Passing through." >&2
  exit 0
fi
debug "TRANSCRIPT_PATH=$TRANSCRIPT_PATH"

if [[ ! -f "$TRANSCRIPT_PATH" ]]; then
  debug "TRANSCRIPT NOT FOUND — exiting"
  echo "VGL: Transcript file not found at $TRANSCRIPT_PATH" >&2
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi
debug "TRANSCRIPT exists, size=$(wc -c < "$TRANSCRIPT_PATH")"

# Search entire transcript for the completion token
EXTRACTED_TOKEN=$(grep --no-filename -oP 'VGL_COMPLETE_[a-f0-9]{32}' "$TRANSCRIPT_PATH" 2>/dev/null | tail -1 || true)
debug "GREP_TRANSCRIPT_EXTRACTED=$EXTRACTED_TOKEN"
debug "COMPLETION_TOKEN=$COMPLETION_TOKEN"
debug "MATCH=$( [[ "$EXTRACTED_TOKEN" = "$COMPLETION_TOKEN" ]] && echo YES || echo NO )"

if [[ -n "$EXTRACTED_TOKEN" ]] && [[ "$EXTRACTED_TOKEN" = "$COMPLETION_TOKEN" ]]; then
  echo "VGL: Verification complete. Token validated." >&2
  echo "   Session: $SESSION_ID | Iterations: $ITERATION" >&2

  # Plan mode: auto-transition to next task
  PLAN_MODE=$(echo "$FRONTMATTER" | grep '^plan_mode:' | sed 's/plan_mode: *//' || echo "false")
  PLAN_FILE=".claude/plan/plan.yaml"

  if [[ "$PLAN_MODE" == "true" ]] && [[ -f "$PLAN_FILE" ]]; then
    PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"

    # Transition: mark current task complete, get next task JSON
    NEXT_JSON=""
    TRANSITION_EXIT=0
    NEXT_JSON=$("${PLUGIN_ROOT}/scripts/transition-task.sh" 2>/dev/null) || TRANSITION_EXIT=$?

    if [[ $TRANSITION_EXIT -eq 0 ]] && [[ -n "$NEXT_JSON" ]] && [[ "$NEXT_JSON" != "null" ]]; then
      NEXT_ID=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
      NEXT_NAME=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])" 2>/dev/null || echo "")
      NEXT_TEST_CMD=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['tests']['quantitative']['command'])" 2>/dev/null || echo "")
      NEXT_PROMPT_FILE=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['prompt_file'])" 2>/dev/null || echo "")
      NEXT_QUAL_CRITERIA=$(echo "$NEXT_JSON" | python3 -c "
import sys, json
t = json.load(sys.stdin)
criteria = t.get('tests',{}).get('qualitative',{}).get('criteria',[])
for c in criteria:
    print(f'- {c}')
" 2>/dev/null || echo "")

      # Check if an integration check is needed before this task
      NEEDS_INTEGRATION=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('_integration_check_before', False))" 2>/dev/null || echo "False")
      INTEGRATION_PREFIX=""
      if [[ "$NEEDS_INTEGRATION" == "True" ]]; then
        echo "VGL: Integration check required before next phase" >&2
        INTEGRATION_PREFIX="INTEGRATION CHECK REQUIRED:
Before starting this task, spawn an integration-checker agent to verify cross-phase wiring:
  Task(subagent_type='integration-checker', prompt='Verify integration between all completed phases. Check cross-phase links, data flows, type contracts, and dead endpoints. Report PASS or NEEDS_FIXES with details.')
If the integration check reports NEEDS_FIXES with CRITICAL issues, fix them before proceeding to this task. WARNING-level issues can be noted and addressed later.

"
      fi

      echo "VGL: Auto-transitioning to: $NEXT_ID - $NEXT_NAME" >&2

      FULL_PROMPT_PATH=".claude/plan/${NEXT_PROMPT_FILE}"
      if [[ -n "$NEXT_PROMPT_FILE" ]] && [[ -f "$FULL_PROMPT_PATH" ]]; then
        NEXT_TASK_PROMPT=$(cat "$FULL_PROMPT_PATH")
      else
        NEXT_TASK_PROMPT="Implement task $NEXT_ID: $NEXT_NAME"
      fi

      RAW_NEXT_TASK_PROMPT="$NEXT_TASK_PROMPT"

      # Query learnings from previous runs (graceful degradation if missing/empty)
      LEARNINGS_PREFIX=""
      LEARNINGS_SCRIPT="${PLUGIN_ROOT}/scripts/learnings.py"
      LEARNINGS_STORAGE=".planning/learnings.jsonl"
      if [[ -f "$LEARNINGS_SCRIPT" ]] && [[ -f "$LEARNINGS_STORAGE" ]]; then
        # Build task context JSON from next task info
        TASK_CONTEXT=$(echo "$NEXT_JSON" | python3 -c "
import sys, json
task = json.load(sys.stdin)
# Extract file patterns from deliverables and prompt file
file_patterns = []
prompt_file = task.get('prompt_file', '')
if prompt_file:
    file_patterns.append(prompt_file)
# Infer task_type from deliverables
deliverables = task.get('deliverables', {})
task_type = 'general'
if deliverables.get('backend') and not deliverables.get('frontend'):
    task_type = 'backend'
elif deliverables.get('frontend') and not deliverables.get('backend'):
    task_type = 'frontend'
elif deliverables.get('backend') and deliverables.get('frontend'):
    task_type = 'backend'
print(json.dumps({'file_patterns': file_patterns, 'task_type': task_type}))
" 2>/dev/null || echo '{}')

        if [[ -n "$TASK_CONTEXT" ]] && [[ "$TASK_CONTEXT" != "{}" ]]; then
          LEARNINGS_OUTPUT=$(python3 "$LEARNINGS_SCRIPT" --relevant "$TASK_CONTEXT" --storage "$LEARNINGS_STORAGE" 2>/dev/null || echo '{"learnings":[],"formatted":""}')
          LEARNINGS_TEXT=$(echo "$LEARNINGS_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
formatted = data.get('formatted', '')
if formatted:
    print(formatted)
" 2>/dev/null || echo "")

          if [[ -n "$LEARNINGS_TEXT" ]]; then
            LEARNINGS_PREFIX="LEARNINGS FROM PREVIOUS RUNS:
${LEARNINGS_TEXT}

"
          fi
        fi
      fi

      NEXT_TASK_PROMPT="${LEARNINGS_PREFIX}${INTEGRATION_PREFIX}CRITICAL RULES — VIOLATION WILL BREAK THE LOOP:
- Do NOT modify .claude/plan/plan.yaml or any .claude/ state files
- Do NOT mark tasks as done or completed — the system handles all transitions
- Do NOT edit .claude/verifier-loop.local.md or .claude/verifier-token.secret

TDD-FIRST WORKFLOW:
1. Read task-{id}.md for full specification and must_haves
2. Write ALL tests first (Red phase)
3. Read the Test Dependency Graph from the task prompt
4. Wave 1: launch fresh agents for independent tests (1 per test with guidance)
5. Wave 2+: continue prior agent sessions for dependent tests
6. wait_for_completion() after each wave, answer agent questions if input_required
7. Run full test suite (Green phase)
8. If tests fail, fix and retry
9. When ready, spawn Verifier subagent from .claude/verifier-prompt.local.md

YOUR TASK:
$NEXT_TASK_PROMPT"

      python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan, save_plan
plan = load_plan('$PLAN_FILE')
for phase in plan.get('phases', []):
    for task in phase.get('tasks', []):
        if str(task['id']) == '$NEXT_ID':
            task['status'] = 'in_progress'
save_plan('$PLAN_FILE', plan)
" 2>/dev/null || true

      rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"

      export _VGL_TASK_PROMPT="$NEXT_TASK_PROMPT"
      export _VGL_RAW_TASK_PROMPT="$RAW_NEXT_TASK_PROMPT"
      export _VGL_TEST_CMD="$NEXT_TEST_CMD"
      export _VGL_QUAL_CRITERIA="$NEXT_QUAL_CRITERIA"
      export _VGL_TASK_ID="$NEXT_ID"
      export _VGL_NEXT_JSON="$NEXT_JSON"
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
    "task_json": os.environ["_VGL_NEXT_JSON"],
    "task_prompt_content": os.environ["_VGL_RAW_TASK_PROMPT"],
}))
PYEOF
)

      SETUP_OUTPUT=$("${PLUGIN_ROOT}/scripts/setup-verifier-loop.sh" --from-json "$SETUP_JSON" 2>&1)
      echo "$SETUP_OUTPUT" >&2

      NEW_STATE_FILE=".claude/verifier-loop.local.md"
      if [[ -f "$NEW_STATE_FILE" ]]; then
        NEW_PROMPT=$(awk '/^---$/{i++; next} i>=2' "$NEW_STATE_FILE")
      else
        NEW_PROMPT="$NEXT_TASK_PROMPT"
      fi

      jq -n \
        --arg prompt "$NEW_PROMPT" \
        --arg msg "VGL auto-transition: starting task $NEXT_ID - $NEXT_NAME | TDD-first: write tests, spawn opencode agents, then verify" \
        '{
          "decision": "block",
          "reason": $prompt,
          "systemMessage": $msg
        }'

      exit 0

    elif [[ $TRANSITION_EXIT -eq 2 ]]; then
      echo "VGL: ALL PLAN TASKS COMPLETE" >&2
      rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
      exit 0
    else
      echo "VGL: Transition error (exit=$TRANSITION_EXIT)" >&2
      rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
      exit 0
    fi
  fi

  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

# Token mismatch — forgery or corruption
if [[ -n "$EXTRACTED_TOKEN" ]]; then
  echo "VGL: INVALID TOKEN - forgery attempt or corruption" >&2
fi

# Not complete — continue loop with SAME PROMPT
NEXT_ITERATION=$((ITERATION + 1))

PROMPT_TEXT=$(awk '/^---$/{i++; next} i>=2' "$STATE_FILE")

if [[ -z "$PROMPT_TEXT" ]]; then
  echo "VGL: State file has no prompt text" >&2
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

# Update iteration in frontmatter
TEMP_FILE="${STATE_FILE}.tmp.$$"
sed "s/^iteration: .*/iteration: $NEXT_ITERATION/" "$STATE_FILE" > "$TEMP_FILE"
mv "$TEMP_FILE" "$STATE_FILE"

# Build system message
if [[ $MAX_ITERATIONS -gt 0 ]]; then
  SYSTEM_MSG="VGL iteration $NEXT_ITERATION/$MAX_ITERATIONS | TDD-first: write tests, spawn opencode, then verify | Token has 128-bit entropy"
else
  SYSTEM_MSG="VGL iteration $NEXT_ITERATION | TDD-first: write tests, spawn opencode, then verify | Token has 128-bit entropy"
fi

echo "VGL: Continuing loop (iteration $NEXT_ITERATION)." >&2

jq -n \
  --arg prompt "$PROMPT_TEXT" \
  --arg msg "$SYSTEM_MSG" \
  '{
    "decision": "block",
    "reason": $prompt,
    "systemMessage": $msg
  }'

exit 0
