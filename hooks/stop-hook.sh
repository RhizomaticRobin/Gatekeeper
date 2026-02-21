#!/bin/bash

# Gatekeeper Stop Hook
# Prevents session exit when a verifier-loop is active
# Feeds the prompt back to continue the loop until verification passes
# Enhanced with must_haves phase auto-transition and TDD signal tracking

set -euo pipefail

PLUGIN_ROOT_LOG="$(dirname "$(dirname "$(realpath "$0")")")"
source "${PLUGIN_ROOT_LOG}/scripts/gk_log.sh"

DEBUG_LOG="/tmp/gatekeeper-stop-hook.debug.log"
debug() { echo "[$(date +%H:%M:%S)] $*" >> "$DEBUG_LOG" 2>/dev/null || true; }
debug "=== STOP HOOK FIRED ==="
debug "PWD=$(pwd)"

# Read hook input from stdin
HOOK_INPUT=$(cat)
debug "HOOK_INPUT_LEN=${#HOOK_INPUT}"
debug "HOOK_INPUT=$(echo "$HOOK_INPUT" | head -c 500)"

# Team mode: lead handles lifecycle, skip Gatekeeper processing
if [[ -f ".claude/gk-team-active" ]]; then
  debug "TEAM MODE ACTIVE — skipping Gatekeeper processing"
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
  gk_error "Gatekeeper: State file corrupted or empty (no valid frontmatter)."
  echo "  Frontmatter content: $(echo "$FRONTMATTER" | head -c 200)" >&2
  echo "  State preserved at: ${STATE_FILE}.corrupted" >&2
  echo "  Recovery: run /gatekeeper:run-away to reset, then restart your task." >&2
  cp "$STATE_FILE" "${STATE_FILE}.corrupted" 2>/dev/null
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 1
fi

ITERATION=$(echo "$FRONTMATTER" | grep '^iteration:' | sed 's/iteration: *//')
MAX_ITERATIONS=$(echo "$FRONTMATTER" | grep '^max_iterations:' | sed 's/max_iterations: *//')
SESSION_ID=$(echo "$FRONTMATTER" | grep '^session_id:' | sed 's/session_id: *//' | sed 's/^"\(.*\)"$/\1/')

# Handle missing session_id
if [[ -z "$SESSION_ID" ]]; then
  gk_error "Gatekeeper: State file corrupted (missing session_id)."
  echo "  State preserved at: ${STATE_FILE}.corrupted" >&2
  echo "  Recovery: run /gatekeeper:run-away to reset, then restart your task." >&2
  cp "$STATE_FILE" "${STATE_FILE}.corrupted" 2>/dev/null
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 1
fi

# Stale session detection: warn and cleanup if started_at > 24h ago
STARTED_AT=$(echo "$FRONTMATTER" | grep '^started_at:' | sed 's/started_at: *//' | sed 's/^"\(.*\)"$/\1/')
if [[ -n "$STARTED_AT" ]]; then
  STARTED_EPOCH=$(date -d "$STARTED_AT" +%s 2>/dev/null || date -jf "%Y-%m-%dT%H:%M:%SZ" "$STARTED_AT" +%s 2>/dev/null || echo "0")
  NOW_EPOCH=$(date +%s)
  ELAPSED=$(( NOW_EPOCH - STARTED_EPOCH ))
  if [[ $STARTED_EPOCH -gt 0 ]] && [[ $ELAPSED -gt 86400 ]]; then
    HOURS_AGO=$(( ELAPSED / 3600 ))
    gk_info "Gatekeeper: Stale session detected (started ${HOURS_AGO}h ago, session: ${SESSION_ID}). Cleaning up."
    echo "  Recovery: run /gatekeeper:run-away to reset, then restart your task." >&2
    rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
    exit 0
  fi
fi

# Read completion token from secret file
if [[ ! -f "$TOKEN_FILE" ]]; then
  gk_info "Gatekeeper: Token file not found"
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi
COMPLETION_TOKEN=$(head -1 "$TOKEN_FILE" | tr -d '\n')

# Validate numeric fields
if [[ ! "$ITERATION" =~ ^[0-9]+$ ]]; then
  gk_error "Gatekeeper: State file corrupted (invalid iteration: '$ITERATION')"
  echo "  State preserved at: ${STATE_FILE}.corrupted" >&2
  cp "$STATE_FILE" "${STATE_FILE}.corrupted" 2>/dev/null
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 1
fi

if [[ ! "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
  gk_error "Gatekeeper: State file corrupted (invalid max_iterations: '$MAX_ITERATIONS')"
  echo "  State preserved at: ${STATE_FILE}.corrupted" >&2
  cp "$STATE_FILE" "${STATE_FILE}.corrupted" 2>/dev/null
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 1
fi

# Validate token format
if [[ ! "$COMPLETION_TOKEN" =~ ^GK_COMPLETE_[a-f0-9]{32}$ ]]; then
  gk_error "Gatekeeper: Token corrupted (value: '${COMPLETION_TOKEN:0:20}...')"
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 1
fi

# Check max iterations
if [[ $MAX_ITERATIONS -gt 0 ]] && [[ $ITERATION -ge $MAX_ITERATIONS ]]; then
  gk_info "Gatekeeper: Max iterations ($MAX_ITERATIONS) reached. Session: $SESSION_ID"
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

# Get transcript path from hook input
TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path') || {
  gk_error "Gatekeeper: Failed to parse transcript_path from hook input"
  TRANSCRIPT_PATH=""
}
if [[ -z "$TRANSCRIPT_PATH" ]] || [[ "$TRANSCRIPT_PATH" == "null" ]]; then
  debug "MALFORMED OR MISSING JSON INPUT — passthrough"
  gk_info "Gatekeeper: Malformed hook input (could not parse transcript_path). Passing through."
  exit 0
fi
debug "TRANSCRIPT_PATH=$TRANSCRIPT_PATH"

if [[ ! -f "$TRANSCRIPT_PATH" ]]; then
  debug "TRANSCRIPT NOT FOUND — exiting"
  gk_info "Gatekeeper: Transcript file not found at $TRANSCRIPT_PATH"
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi
debug "TRANSCRIPT exists, size=$(wc -c < "$TRANSCRIPT_PATH")"

# Search entire transcript for the completion token
EXTRACTED_TOKEN=$(grep --no-filename -oP 'GK_COMPLETE_[a-f0-9]{32}' "$TRANSCRIPT_PATH" 2>/dev/null | tail -1 || true)
debug "GREP_TRANSCRIPT_EXTRACTED=$EXTRACTED_TOKEN"
debug "COMPLETION_TOKEN=$COMPLETION_TOKEN"
debug "MATCH=$( [[ "$EXTRACTED_TOKEN" = "$COMPLETION_TOKEN" ]] && echo YES || echo NO )"

if [[ -n "$EXTRACTED_TOKEN" ]] && [[ "$EXTRACTED_TOKEN" = "$COMPLETION_TOKEN" ]]; then
  gk_info "Gatekeeper: Verification complete. Token validated."
  echo "   Session: $SESSION_ID | Iterations: $ITERATION" >&2

  # Reset resilience state on success
  RESILIENCE_PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
  RESILIENCE_SCRIPT="${RESILIENCE_PLUGIN_ROOT}/scripts/resilience.py"
  RESILIENCE_STATE=".claude/gk-resilience.json"
  RESILIENCE_TASK_ID=$(echo "$FRONTMATTER" | grep '^task_id:' | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/')
  if [[ -f "$RESILIENCE_SCRIPT" ]]; then
    if ! python3 "$RESILIENCE_SCRIPT" --state-path "$RESILIENCE_STATE" --record-success "$RESILIENCE_TASK_ID" 2>&1; then
      gk_warn "Failed to record resilience success for task $RESILIENCE_TASK_ID"
    fi
    if ! python3 "$RESILIENCE_SCRIPT" --state-path "$RESILIENCE_STATE" --reset 2>&1; then
      gk_warn "Failed to reset resilience state"
    fi
  fi

  # Plan mode: auto-transition to next task
  PLAN_MODE=$(echo "$FRONTMATTER" | grep '^plan_mode:' | sed 's/plan_mode: *//' || echo "false")
  PLAN_FILE=".claude/plan/plan.yaml"

  if [[ "$PLAN_MODE" == "true" ]] && [[ -f "$PLAN_FILE" ]]; then
    PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"

    # Transition: mark current task complete, get next task JSON
    NEXT_JSON=""
    TRANSITION_EXIT=0
    NEXT_JSON=$("${PLUGIN_ROOT}/scripts/transition-task.sh") || TRANSITION_EXIT=$?

    if [[ $TRANSITION_EXIT -eq 0 ]] && [[ -n "$NEXT_JSON" ]] && [[ "$NEXT_JSON" != "null" ]]; then
      NEXT_ID=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])") || {
        gk_error "Gatekeeper: Failed to parse next task ID from transition output"
        exit 1
      }
      NEXT_NAME=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])") || {
        gk_error "Gatekeeper: Failed to parse next task name from transition output"
        exit 1
      }
      NEXT_TEST_CMD=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['tests']['quantitative']['command'])") || {
        gk_error "Gatekeeper: Next task missing tests.quantitative.command"
        exit 1
      }
      NEXT_PROMPT_FILE=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['prompt_file'])") || {
        gk_error "Gatekeeper: Next task missing prompt_file"
        exit 1
      }
      NEXT_QUAL_CRITERIA=$(echo "$NEXT_JSON" | python3 -c "
import sys, json
t = json.load(sys.stdin)
criteria = t.get('tests',{}).get('qualitative',{}).get('criteria',[])
for c in criteria:
    print(f'- {c}')
") || NEXT_QUAL_CRITERIA=""

      # Check if an integration check is needed before this task
      NEEDS_INTEGRATION=$(echo "$NEXT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('_integration_check_before', False))") || {
        gk_warn "Could not determine integration check status for next task"
        NEEDS_INTEGRATION="False"
      }
      INTEGRATION_PREFIX=""
      if [[ "$NEEDS_INTEGRATION" == "True" ]]; then
        gk_info "Gatekeeper: Integration check required before next phase"
        INTEGRATION_PREFIX="INTEGRATION CHECK REQUIRED:
Before starting this task, spawn an integration-checker agent to verify cross-phase wiring:
  Task(subagent_type='integration-checker', prompt='Verify integration between all completed phases. Check cross-phase links, data flows, type contracts, and dead endpoints. Report PASS or NEEDS_FIXES with details.')
If the integration check reports NEEDS_FIXES with CRITICAL issues, fix them before proceeding to this task. WARNING-level issues can be noted and addressed later.

"
      fi

      gk_info "Gatekeeper: Auto-transitioning to: $NEXT_ID - $NEXT_NAME"

      FULL_PROMPT_PATH=".claude/plan/${NEXT_PROMPT_FILE}"
      if [[ -n "$NEXT_PROMPT_FILE" ]] && [[ -f "$FULL_PROMPT_PATH" ]]; then
        NEXT_TASK_PROMPT=$(cat "$FULL_PROMPT_PATH")
      else
        NEXT_TASK_PROMPT="Implement task $NEXT_ID: $NEXT_NAME"
      fi

      RAW_NEXT_TASK_PROMPT="$NEXT_TASK_PROMPT"

      # Build evolution context for next task (replaces LEARNINGS_PREFIX)
      EVOLUTION_PREFIX=""
      NEXT_TASK_ID="$NEXT_ID"
      NEXT_EVO_DB_PATH=".planning/evolution/${NEXT_TASK_ID}/"
      EVO_PROMPT_SCRIPT="${PLUGIN_ROOT}/scripts/evo_prompt.py"
      if [[ -f "$EVO_PROMPT_SCRIPT" ]] && [[ -d "$NEXT_EVO_DB_PATH" ]] && [[ -n "$NEXT_TASK_ID" ]]; then
        EVO_CONTEXT=$(python3 "$EVO_PROMPT_SCRIPT" --build "$NEXT_EVO_DB_PATH" "$NEXT_TASK_ID" 2>&1) || {
          gk_warn "Evolution context generation failed for task $NEXT_TASK_ID, proceeding without evolutionary intelligence"
          EVO_CONTEXT=""
        }
        if [[ -n "$EVO_CONTEXT" ]]; then
          EVOLUTION_PREFIX="EVOLUTION CONTEXT:
${EVO_CONTEXT}

"
        fi
      fi

      NEXT_TASK_PROMPT="${EVOLUTION_PREFIX}${INTEGRATION_PREFIX}CRITICAL RULES — VIOLATION WILL BREAK THE LOOP:
- Do NOT modify .claude/plan/plan.yaml or any .claude/ state files
- Do NOT mark tasks as done or completed — the system handles all transitions
- Do NOT edit .claude/verifier-loop.local.md or .claude/verifier-token.secret

TDD-FIRST WORKFLOW:
1. Read task-{id}.md for full specification and must_haves
2. Write ALL tests first (Red phase)
3. Read the Test Dependency Graph from the task prompt
4. Implement code following test dependency graph and guidance
5. Run full test suite (Green phase)
6. If tests fail, fix and retry
7. When ready, spawn Verifier subagent from .claude/verifier-prompt.local.md

YOUR TASK:
$NEXT_TASK_PROMPT"

      if ! python3 "${PLUGIN_ROOT}/scripts/plan_utils.py" "$PLAN_FILE" --start-task "$NEXT_ID" 2>&1; then
        gk_warn "Failed to mark task $NEXT_ID as in_progress in plan.yaml"
      fi

      rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"

      export _GK_TASK_PROMPT="$NEXT_TASK_PROMPT"
      export _GK_RAW_TASK_PROMPT="$RAW_NEXT_TASK_PROMPT"
      export _GK_TEST_CMD="$NEXT_TEST_CMD"
      export _GK_QUAL_CRITERIA="$NEXT_QUAL_CRITERIA"
      export _GK_TASK_ID="$NEXT_ID"
      export _GK_NEXT_JSON="$NEXT_JSON"
      SETUP_JSON=$(python3 << 'PYEOF'
import json, os
print(json.dumps({
    "prompt": os.environ["_GK_TASK_PROMPT"],
    "verification_criteria": "Quantitative: {} must pass\nQualitative:\n{}".format(
        os.environ["_GK_TEST_CMD"], os.environ["_GK_QUAL_CRITERIA"]),
    "test_command": os.environ["_GK_TEST_CMD"],
    "verifier_model": "sonnet",
    "max_iterations": 0,
    "plan_mode": True,
    "task_id": os.environ["_GK_TASK_ID"],
    "task_json": os.environ["_GK_NEXT_JSON"],
    "task_prompt_content": os.environ["_GK_RAW_TASK_PROMPT"],
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
        --arg msg "Gatekeeper auto-transition: starting task $NEXT_ID - $NEXT_NAME | TDD-first: write tests, implement, then verify" \
        '{
          "decision": "block",
          "reason": $prompt,
          "systemMessage": $msg
        }'

      exit 0

    elif [[ $TRANSITION_EXIT -eq 2 ]]; then
      gk_info "Gatekeeper: ALL PLAN TASKS COMPLETE"
      rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
      rm -f ".claude/plan-locked"
      exit 0
    else
      gk_info "Gatekeeper: Transition error (exit=$TRANSITION_EXIT)"
      rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
      exit 0
    fi
  fi

  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

# Token mismatch — forgery or corruption
if [[ -n "$EXTRACTED_TOKEN" ]]; then
  gk_info "Gatekeeper: INVALID TOKEN - forgery attempt or corruption"
fi

# --- Evolution: evaluate this iteration's attempt ---
PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
TASK_ID=$(echo "$FRONTMATTER" | grep '^task_id:' | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/') || TASK_ID=""
if [[ -z "$TASK_ID" ]]; then
  gk_warn "No task_id in Gatekeeper state frontmatter — evolution tracking disabled for this iteration"
fi
PLAN_FILE=".claude/plan/plan.yaml"
SCRIPTS_DIR="${PLUGIN_ROOT}/scripts"
EVO_DB_PATH=".planning/evolution/${TASK_ID}/"
TEST_COMMAND=$(echo "$FRONTMATTER" | grep '^test_command:' | sed 's/test_command: *//' | sed 's/^"\(.*\)"$/\1/') || TEST_COMMAND=""
if [[ -z "$TEST_COMMAND" ]]; then
  gk_warn "No test_command in Gatekeeper state frontmatter — evaluation disabled for this iteration"
fi

# Create population dir on first iteration
if [[ ! -d "$EVO_DB_PATH" ]]; then
  mkdir -p "$EVO_DB_PATH"
  debug "Gatekeeper: Created population directory $EVO_DB_PATH"
fi

# Evaluate current attempt
EVO_EVAL_SCRIPT="${PLUGIN_ROOT}/scripts/evo_eval.py"
EVAL_METRICS="{}"
if [[ -f "$EVO_EVAL_SCRIPT" ]] && [[ -n "$TEST_COMMAND" ]]; then
  debug "Gatekeeper: Evaluating iteration attempt"
  gk_info "Gatekeeper: Evaluating iteration attempt"
  EVAL_METRICS=$(python3 "$EVO_EVAL_SCRIPT" --evaluate "$TEST_COMMAND" 2>&1) || {
    gk_warn "Evaluation failed for iteration $ITERATION — metrics unavailable"
    EVAL_METRICS="{}"
  }
  debug "Gatekeeper: Eval metrics: $EVAL_METRICS"

  # Store in population — restructure flat eval metrics into Approach format
  EVO_DB_SCRIPT="${PLUGIN_ROOT}/scripts/evo_db.py"
  if [[ -f "$EVO_DB_SCRIPT" ]] && [[ "$EVAL_METRICS" != "{}" ]]; then
    debug "Gatekeeper: Storing evaluation in population"
    gk_info "Gatekeeper: Stored in population"
    APPROACH_JSON=$(python3 -c "
import json, sys
metrics = json.loads(sys.argv[1])
artifacts = metrics.pop('artifacts', {})
stage = metrics.pop('stage', 0)
print(json.dumps({
    'metrics': metrics,
    'artifacts': artifacts,
    'task_id': sys.argv[2],
    'iteration': int(sys.argv[3]),
}))
" "$EVAL_METRICS" "$TASK_ID" "$ITERATION" 2>&1) || {
      gk_warn "Failed to build approach JSON for population storage"
      APPROACH_JSON="{}"
    }
    if [[ "$APPROACH_JSON" != "{}" ]]; then
      if ! python3 "$EVO_DB_SCRIPT" --db-path "$EVO_DB_PATH" --add "$APPROACH_JSON" 2>&1; then
        gk_warn "Failed to store approach in evolution population DB"
      fi
    fi
  fi
fi

# Pollinate on first iteration
if [[ "$ITERATION" == "1" ]] || [[ "$ITERATION" == "0" ]]; then
  EVO_POLLINATOR="${PLUGIN_ROOT}/scripts/evo_pollinator.py"
  PLAN_FILE=".claude/plan/plan.yaml"
  if [[ -f "$EVO_POLLINATOR" ]] && [[ -f "$PLAN_FILE" ]] && [[ -n "$TASK_ID" ]]; then
    debug "Gatekeeper: Pollinating from similar tasks"
    gk_info "Gatekeeper: Pollinating from similar tasks"
    if ! python3 "$EVO_POLLINATOR" --pollinate "$EVO_DB_PATH" "$PLAN_FILE" "$TASK_ID" 2>&1; then
      gk_warn "Cross-task pollination failed for task $TASK_ID"
    fi
  fi
fi

# Build evolution context for next iteration (replaces LEARNINGS_PREFIX)
EVOLUTION_PREFIX=""
EVO_PROMPT_SCRIPT="${PLUGIN_ROOT}/scripts/evo_prompt.py"
if [[ -f "$EVO_PROMPT_SCRIPT" ]] && [[ -d "$EVO_DB_PATH" ]] && [[ -n "$TASK_ID" ]]; then
  EVO_CONTEXT=$(python3 "$EVO_PROMPT_SCRIPT" --build "$EVO_DB_PATH" "$TASK_ID" 2>&1) || {
    gk_warn "Evolution context generation failed for retry iteration, proceeding without"
    EVO_CONTEXT=""
  }
  if [[ -n "$EVO_CONTEXT" ]]; then
    EVOLUTION_PREFIX="EVOLUTION CONTEXT:
${EVO_CONTEXT}

"
  fi
fi

# --- Resilience: check if we should stop ---
RESILIENCE_SCRIPT="${PLUGIN_ROOT}/scripts/resilience.py"
RESILIENCE_STATE=".claude/gk-resilience.json"
if [[ -f "$RESILIENCE_SCRIPT" ]]; then
  # Record the failure
  if ! python3 "$RESILIENCE_SCRIPT" --state-path "$RESILIENCE_STATE" \
    --record-failure "$TASK_ID" 2>&1; then
    gk_warn "Failed to record resilience failure for task $TASK_ID"
  fi

  # Read resilience config from plan.yaml metadata
  RESILIENCE_CONFIG=$(python3 -c "
import sys, json
sys.path.insert(0, '${SCRIPTS_DIR}')
from plan_utils import load_plan
plan = load_plan('$PLAN_FILE')
meta = plan.get('metadata', {})
config = {}
for key in ('stuck_threshold', 'circuit_breaker_threshold', 'max_gatekeeper_iterations', 'timeout_hours'):
    if key in meta:
        config[key] = meta[key]
    else:
        raise KeyError(f'Required resilience config key missing from plan metadata: {key}')
print(json.dumps(config))
" 2>&1) || {
    gk_warn "Failed to read resilience config from plan metadata — using hardcoded defaults"
    RESILIENCE_CONFIG='{"stuck_threshold":3,"circuit_breaker_threshold":5,"max_gatekeeper_iterations":50,"timeout_hours":8}'
  }

  # Check all resilience conditions
  RESILIENCE_CHECK_OUTPUT=""
  RESILIENCE_CHECK_OUTPUT=$(python3 "$RESILIENCE_SCRIPT" --state-path "$RESILIENCE_STATE" \
    --check-all "$TASK_ID" --config "$RESILIENCE_CONFIG" 2>&1) || {
    RESILIENCE_EXIT=$?
    if [[ $RESILIENCE_EXIT -eq 1 ]]; then
      gk_info "Gatekeeper: $RESILIENCE_CHECK_OUTPUT"
      gk_info "Gatekeeper: Stopping due to resilience check failure."
      rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
      exit 0
    fi
  }
fi

# Not complete — continue loop with SAME PROMPT
NEXT_ITERATION=$((ITERATION + 1))

PROMPT_TEXT=$(awk '/^---$/{i++; next} i>=2' "$STATE_FILE")

if [[ -z "$PROMPT_TEXT" ]]; then
  gk_info "Gatekeeper: State file has no prompt text"
  rm -f "$STATE_FILE" ".claude/verifier-prompt.local.md" "$TOKEN_FILE"
  exit 0
fi

# Prepend evolution context to prompt
PROMPT_TEXT="${EVOLUTION_PREFIX}${PROMPT_TEXT}"

# Update iteration in frontmatter
TEMP_FILE="${STATE_FILE}.tmp.$$"
sed "s/^iteration: .*/iteration: $NEXT_ITERATION/" "$STATE_FILE" > "$TEMP_FILE"
mv "$TEMP_FILE" "$STATE_FILE"

# Build system message
if [[ $MAX_ITERATIONS -gt 0 ]]; then
  SYSTEM_MSG="Gatekeeper iteration $NEXT_ITERATION/$MAX_ITERATIONS | Evolution-guided | TDD-first: write tests, implement, then verify | Token has 128-bit entropy"
else
  SYSTEM_MSG="Gatekeeper iteration $NEXT_ITERATION | Evolution-guided | TDD-first: write tests, implement, then verify | Token has 128-bit entropy"
fi

gk_info "Gatekeeper: Continuing loop (iteration $NEXT_ITERATION)."

jq -n \
  --arg prompt "$PROMPT_TEXT" \
  --arg msg "$SYSTEM_MSG" \
  '{
    "decision": "block",
    "reason": $prompt,
    "systemMessage": $msg
  }'

exit 0
