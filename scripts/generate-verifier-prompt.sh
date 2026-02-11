#!/bin/bash

# Generate Verifier Prompt Script (GSD-VGL)
#
# Builds the immutable verifier prompt from plan.yaml metadata + task must_haves
# + qualitative criteria + Playwright steps. Called by setup-verifier-loop.sh.
#
# NOT accessible to executor agents — this script runs at VGL setup time only.
#
# Usage:
#   generate-verifier-prompt.sh --task-json <json> --plan-file <path> \
#     --fetch-script <path> --session-dir <dir> --project-dir <dir> \
#     [--task-prompt-content <text>]
#
# Output: writes to <session-dir>/verifier-prompt.local.md

set -euo pipefail

TASK_JSON=""
PLAN_FILE=""
FETCH_SCRIPT=""
SESSION_DIR=""
PROJECT_DIR=""
TASK_PROMPT_CONTENT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-json) TASK_JSON="$2"; shift 2 ;;
    --plan-file) PLAN_FILE="$2"; shift 2 ;;
    --fetch-script) FETCH_SCRIPT="$2"; shift 2 ;;
    --session-dir) SESSION_DIR="$2"; shift 2 ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    --task-prompt-content) TASK_PROMPT_CONTENT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$TASK_JSON" ]] || [[ -z "$SESSION_DIR" ]] || [[ -z "$FETCH_SCRIPT" ]]; then
  echo "Error: --task-json, --session-dir, and --fetch-script are required" >&2
  exit 1
fi

# Extract task metadata
TASK_NAME=$(echo "$TASK_JSON" | python3 -c "
import sys, json
try:
    t = json.load(sys.stdin)
    print(t.get('name', ''))
except: print('')
" 2>/dev/null || echo "")

TASK_DELIVERABLES=$(echo "$TASK_JSON" | python3 -c "
import sys, json
try:
    t = json.load(sys.stdin)
    d = t.get('deliverables', {})
    if d.get('backend'):
        print(f'Backend: {d[\"backend\"]}')
    if d.get('frontend'):
        print(f'Frontend: {d[\"frontend\"]}')
except: pass
" 2>/dev/null || echo "")

TEST_COMMAND=$(echo "$TASK_JSON" | python3 -c "
import sys, json
try:
    t = json.load(sys.stdin)
    print(t.get('tests',{}).get('quantitative',{}).get('command',''))
except: print('')
" 2>/dev/null || echo "")

QUAL_URL=$(echo "$TASK_JSON" | python3 -c "
import sys, json
try:
    t = json.load(sys.stdin)
    print(t.get('tests',{}).get('qualitative',{}).get('playwright_url',''))
except: print('')
" 2>/dev/null || echo "")

QUAL_CRITERIA=$(echo "$TASK_JSON" | python3 -c "
import sys, json
try:
    t = json.load(sys.stdin)
    criteria = t.get('tests',{}).get('qualitative',{}).get('criteria',[])
    for c in criteria:
        print(f'- {c}')
except: pass
" 2>/dev/null || echo "")

# Extract must_haves from task JSON
MUST_HAVES=$(echo "$TASK_JSON" | python3 -c "
import sys, json
try:
    t = json.load(sys.stdin)
    mh = t.get('must_haves', {})
    if mh:
        truths = mh.get('truths', [])
        artifacts = mh.get('artifacts', [])
        key_links = mh.get('key_links', [])
        if truths:
            print('TRUTHS (user-observable behaviors that must work):')
            for truth in truths:
                print(f'  - {truth}')
        if artifacts:
            print('ARTIFACTS (files with real implementation):')
            for art in artifacts:
                print(f'  - {art}')
        if key_links:
            print('KEY LINKS (critical connections):')
            for link in key_links:
                print(f'  - {link}')
except: pass
" 2>/dev/null || echo "")

# Read dev server URL from plan.yaml
DEV_SERVER_URL=""
if [[ -n "$PLAN_FILE" ]] && [[ -f "$PLAN_FILE" ]]; then
  PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
  DEV_SERVER_URL=$(python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan
plan = load_plan('$PLAN_FILE')
print(plan.get('metadata',{}).get('dev_server_url',''))
" 2>/dev/null || echo "")
fi

# Build the verifier prompt
cat > "${SESSION_DIR}/verifier-prompt.local.md" <<PLANEOF
You are a VERIFICATION AGENT with VISUAL TESTING AUTHORITY.

TASK UNDER VERIFICATION: $TASK_NAME

EXPECTED DELIVERABLES:
$TASK_DELIVERABLES

PLANEOF

# Add must_haves section if present
if [[ -n "$MUST_HAVES" ]]; then
  cat >> "${SESSION_DIR}/verifier-prompt.local.md" <<MHEOF
MUST-HAVES (goal-backward verification criteria):
$MUST_HAVES

MHEOF
fi

cat >> "${SESSION_DIR}/verifier-prompt.local.md" <<PLANEOF
QUANTITATIVE CRITERIA:
- Run test command: cd $PROJECT_DIR && $TEST_COMMAND

QUALITATIVE CRITERIA (Playwright visual verification required):
$QUAL_CRITERIA
PLANEOF

# Append full task prompt if available
if [[ -n "$TASK_PROMPT_CONTENT" ]]; then
  cat >> "${SESSION_DIR}/verifier-prompt.local.md" <<TASKEOF

FULL TASK SPECIFICATION (reference for what should have been built):
$TASK_PROMPT_CONTENT
TASKEOF
fi

cat >> "${SESSION_DIR}/verifier-prompt.local.md" <<PLANEOF

STEPS — follow exactly in order:

1. Read and inspect source files in $PROJECT_DIR/
   - Check that ALL deliverables listed above actually exist and are properly implemented
   - Compare the implementation against the full task specification
   - Verify ALL must_haves: truths are observable, artifacts exist, key_links are wired
   - Look for obvious bugs, missing imports, incomplete logic, missing features

2. Run quantitative tests:
   cd $PROJECT_DIR && $TEST_COMMAND

3. Perform Playwright visual verification:
   a. Navigate to ${DEV_SERVER_URL}${QUAL_URL} using browser_navigate
   b. Take a snapshot using browser_snapshot
   c. Choose your own test inputs — use realistic, unpredictable values
   d. For each qualitative criterion, interact with the UI:
      browser_click, browser_type, browser_fill_form as needed
   e. Take screenshots at each step using browser_take_screenshot
   f. Check browser_console_messages for errors
   g. Critically assess every screenshot — broken layouts, missing
      elements, error states, placeholder text = FAIL

4. If ALL quantitative tests pass AND ALL qualitative criteria are satisfied AND all must_haves verified:
   Run: cd $PROJECT_DIR && bash $FETCH_SCRIPT --session-dir ${SESSION_DIR}

OUTPUT: your entire response is one of:
<verification-complete>
PASS: [paste the token from the fetch script here]
</verification-complete>
or
<verification-complete>
FAIL
</verification-complete>

Say nothing else. Your entire response is one of those two blocks. No commentary, no explanation, no analysis.
PLANEOF

echo "Verifier prompt generated at: ${SESSION_DIR}/verifier-prompt.local.md" >&2
