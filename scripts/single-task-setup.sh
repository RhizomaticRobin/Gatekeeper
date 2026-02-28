#!/usr/bin/env bash
set -euo pipefail

# Single-Task Gatekeeper Setup Script
# Called by cross-team command when only 1 unblocked task exists.
#
# Usage: single-task-setup.sh <plugin_root> <task_id>
#
# 1. Reads task details from plan.yaml
# 2. Reads the task prompt file
# 3. Builds the Gatekeeper prompt with TDD-first instructions
# 4. Marks the task as in_progress
# 5. Launches the Gatekeeper loop via setup-verifier-loop.sh
#
# Exit:
#   Outputs "CROSS_OK" on success
#   Outputs "CROSS_TEAM_FAILED" on failure

PLUGIN_ROOT="${1:?Usage: single-task-setup.sh <plugin_root> <task_id>}"
TASK_ID="${2:?Usage: single-task-setup.sh <plugin_root> <task_id>}"
source "${PLUGIN_ROOT}/scripts/gk_log.sh"
PLAN_FILE=".claude/plan/plan.yaml"

# Check plan file
if [[ ! -f "$PLAN_FILE" ]]; then
  gk_error "Plan file not found at $PLAN_FILE"
  echo "CROSS_TEAM_FAILED"
  exit 1
fi

# Get task JSON
TASK_JSON=$(python3 -c "
import sys, json
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan, find_task
plan = load_plan('$PLAN_FILE')
_, task = find_task(plan, '$TASK_ID')
if task is None:
    print('null')
else:
    print(json.dumps(task))
") || {
  gk_error "Failed to extract task $TASK_ID from plan"
  echo "CROSS_TEAM_FAILED"
  exit 1
}

if [[ -z "$TASK_JSON" ]] || [[ "$TASK_JSON" == "null" ]]; then
  gk_error "Task $TASK_ID not found in plan"
  echo "CROSS_TEAM_FAILED"
  exit 1
fi

# Extract task fields
TASK_NAME=$(echo "$TASK_JSON" | python3 -c "import sys,json; t=json.load(sys.stdin); n=t.get('name',''); assert n, 'name is empty'; print(n)") || {
  gk_error "Task $TASK_ID has no 'name' field"
  echo "CROSS_TEAM_FAILED"
  exit 1
}
TEST_CMD=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['tests']['quantitative']['command'])") || {
  gk_error "Task $TASK_ID missing tests.quantitative.command"
  echo "CROSS_TEAM_FAILED"
  exit 1
}
PROMPT_FILE=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['prompt_file'])") || {
  gk_error "Task $TASK_ID missing prompt_file"
  echo "CROSS_TEAM_FAILED"
  exit 1
}

QUAL_CRITERIA=$(echo "$TASK_JSON" | python3 -c "
import sys, json
t = json.load(sys.stdin)
criteria = t.get('tests', {}).get('qualitative', {}).get('criteria', [])
for c in criteria:
    print(f'- {c}')
") || QUAL_CRITERIA=""

MUST_HAVES=$(echo "$TASK_JSON" | python3 -c "
import sys, json
t = json.load(sys.stdin)
mh = t.get('must_haves', {})
truths = mh.get('truths', [])
artifacts = mh.get('artifacts', [])
key_links = mh.get('key_links', [])
if truths:
    print('TRUTHS (invariants that must hold):')
    for tr in truths: print(f'  - {tr}')
if artifacts:
    print('ARTIFACTS (files/outputs that must exist):')
    for a in artifacts: print(f'  - {a}')
if key_links:
    print('KEY LINKS (references):')
    for kl in key_links: print(f'  - {kl}')
") || MUST_HAVES=""

# Read task prompt file
FULL_PROMPT_PATH=".claude/plan/${PROMPT_FILE}"
if [[ -n "$PROMPT_FILE" ]] && [[ -f "$FULL_PROMPT_PATH" ]]; then
  TASK_PROMPT=$(cat "$FULL_PROMPT_PATH")
else
  echo "PROMPT_NOT_FOUND: Task prompt file not found at $FULL_PROMPT_PATH"
  echo "CROSS_TEAM_FAILED"
  exit 0
fi

RAW_TASK_PROMPT="$TASK_PROMPT"

# Build the full Gatekeeper prompt with TDD-first instructions
TASK_PROMPT="CRITICAL RULES — VIOLATION WILL BREAK THE LOOP:
- Do NOT modify .claude/plan/plan.yaml or any .claude/ state files
- Do NOT mark tasks as done or completed — the system handles all transitions
- Do NOT edit .claude/verifier-loop.local.md or .claude/verifier-token.secret

TDD-FIRST WORKFLOW (MANDATORY):
You MUST follow this execution order:
1. Write ALL tests first — unit tests, integration tests, edge cases. Every deliverable gets a test BEFORE any implementation code is written.
2. Run tests to confirm they fail (TDD Red state)
3. Implement the code to make tests pass
4. Run the FULL test suite yourself to verify all tests pass: $TEST_CMD
5. If any tests fail, fix issues and re-run until green.
6. Only THEN spawn the Verifier subagent for final verification.

${MUST_HAVES:+MUST_HAVES FOR THIS TASK:
$MUST_HAVES
}
YOUR TASK:
$TASK_PROMPT"

# Lock plan files — no agent can Write|Edit them during execution
date -u +%Y-%m-%dT%H:%M:%SZ > .claude/plan-locked

# Mark task as in_progress
python3 "${PLUGIN_ROOT}/scripts/plan_utils.py" "$PLAN_FILE" --start-task "$TASK_ID" 2>&1 || {
  gk_warn "Failed to update plan.yaml status for task $TASK_ID"
}

# Build JSON input and launch Gatekeeper loop in plan mode
export _GK_TASK_PROMPT="$TASK_PROMPT"
export _GK_RAW_TASK_PROMPT="$RAW_TASK_PROMPT"
export _GK_TEST_CMD="$TEST_CMD"
export _GK_QUAL_CRITERIA="$QUAL_CRITERIA"
export _GK_TASK_ID="$TASK_ID"
export _GK_NEXT_JSON="$TASK_JSON"
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
) || {
  gk_error "Failed to build setup JSON for task $TASK_ID"
  echo "CROSS_TEAM_FAILED"
  exit 1
}

if [[ -z "$SETUP_JSON" ]]; then
  gk_error "Setup JSON is empty for task $TASK_ID"
  echo "CROSS_TEAM_FAILED"
  exit 1
fi

"${PLUGIN_ROOT}/scripts/setup-verifier-loop.sh" --from-json "$SETUP_JSON" 2>&1 || {
  gk_error "setup-verifier-loop.sh failed for task $TASK_ID"
  echo "CROSS_TEAM_FAILED"
  exit 1
}

echo "CROSS_OK"
