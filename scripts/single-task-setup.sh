#!/usr/bin/env bash
set -euo pipefail

# Single-Task VGL Setup Script (GSD-VGL)
# Called by cross-team command when only 1 unblocked task exists.
#
# Usage: single-task-setup.sh <plugin_root> <task_id>
#
# 1. Reads task details from plan.yaml
# 2. Reads the task prompt file
# 3. Builds the VGL prompt with TDD-first instructions
# 4. Marks the task as in_progress
# 5. Launches the VGL via setup-verifier-loop.sh
#
# Exit:
#   Outputs "CROSS_OK" on success
#   Outputs "CROSS_TEAM_FAILED" on failure

PLUGIN_ROOT="${1:?Usage: single-task-setup.sh <plugin_root> <task_id>}"
TASK_ID="${2:?Usage: single-task-setup.sh <plugin_root> <task_id>}"
PLAN_FILE=".claude/plan/plan.yaml"

# Check plan file
if [[ ! -f "$PLAN_FILE" ]]; then
  echo "PLAN_NOT_FOUND: Plan file not found at $PLAN_FILE"
  echo "CROSS_TEAM_FAILED"
  exit 0
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
" 2>/dev/null) || true

if [[ -z "$TASK_JSON" ]] || [[ "$TASK_JSON" == "null" ]]; then
  echo "TASK_NOT_FOUND: Task $TASK_ID not found in plan"
  echo "CROSS_TEAM_FAILED"
  exit 0
fi

# Extract task fields
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
" 2>/dev/null) || true

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

# Build the full VGL prompt with TDD-first instructions
TASK_PROMPT="CRITICAL RULES — VIOLATION WILL BREAK THE LOOP:
- Do NOT modify .claude/plan/plan.yaml or any .claude/ state files
- Do NOT mark tasks as done or completed — the system handles all transitions
- Do NOT edit .claude/verifier-loop.local.md or .claude/verifier-token.secret

TDD-FIRST + OPENCODE MCP WORKFLOW (MANDATORY):
You MUST follow this execution order:
1. Write ALL tests first — unit tests, integration tests, edge cases. Every deliverable gets a test BEFORE any implementation code is written.
2. Dispatch opencode agents from the Test Dependency Graph — 1 test per agent with guidance. Dispatch in waves respecting test dependencies.
3. Wait for all opencode agents to complete using wait_for_completion MCP tool.
4. Run the FULL test suite yourself to verify all tests pass: $TEST_CMD
5. If any tests fail, fix issues and re-run until green.
6. Only THEN spawn the Verifier subagent for final verification.

${MUST_HAVES:+MUST_HAVES FOR THIS TASK:
$MUST_HAVES
}
YOUR TASK:
$TASK_PROMPT"

# Mark task as in_progress
python3 "${PLUGIN_ROOT}/scripts/plan_utils.py" "$PLAN_FILE" --start-task "$TASK_ID" 2>&1 || true

# Build JSON input and launch VGL in plan mode
export _VGL_TASK_PROMPT="$TASK_PROMPT"
export _VGL_RAW_TASK_PROMPT="$RAW_TASK_PROMPT"
export _VGL_TEST_CMD="$TEST_CMD"
export _VGL_QUAL_CRITERIA="$QUAL_CRITERIA"
export _VGL_TASK_ID="$TASK_ID"
export _VGL_NEXT_JSON="$TASK_JSON"
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
) || true

if [[ -z "$SETUP_JSON" ]]; then
  echo "SETUP_JSON_FAILED: Could not build setup JSON"
  echo "CROSS_TEAM_FAILED"
  exit 0
fi

"${PLUGIN_ROOT}/scripts/setup-verifier-loop.sh" --from-json "$SETUP_JSON" 2>&1 || {
  echo "SETUP_VGL_FAILED: setup-verifier-loop.sh failed"
  echo "CROSS_TEAM_FAILED"
  exit 0
}

echo "CROSS_OK"
