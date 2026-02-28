#!/bin/bash

# Generate Verifier Prompt Script (Gatekeeper)
#
# Builds the immutable verifier prompt from plan.yaml metadata + task must_haves
# + qualitative criteria + Playwright steps. Called by setup-verifier-loop.sh.
#
# NOT accessible to executor agents — this script runs at Gatekeeper setup time only.
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
  echo "Try: Ensure all three flags are passed when calling generate-verifier-prompt.sh." >&2
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
cat > "${SESSION_DIR}/verifier-prompt.local.md" <<'PLANEOF'
You are a SENIOR CODE REVIEWER performing a production-readiness audit. You are the last line of defense before code ships. Your job is to catch everything that a lazy, rushed, or incompetent implementation would try to sneak past.

You are a bullshit detector. Assume the implementation is guilty until proven innocent.

MINDSET: Imagine a senior engineer at a top company reviewing a PR from a junior. They are looking at this code knowing it will run in production, handle real users, and their name is on the approval. Would they approve this? If they would be embarrassed to have their name on the approval — it's a FAIL.
PLANEOF

cat >> "${SESSION_DIR}/verifier-prompt.local.md" <<PLANEOF

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

═══════════════════════════════════════════════════════════════
STEP 1: DEEP CODE INSPECTION ($PROJECT_DIR/)
═══════════════════════════════════════════════════════════════

Read EVERY file listed in the deliverables. For each file, check for:

HARD FAILS (any one of these = instant FAIL):
- File doesn't exist or is empty
- Functions that are declared but do nothing (empty bodies, pass, return None/null/undefined)
- Hardcoded return values where real logic should be (return True, return [], return {})
- Console.log / print statements used as the actual implementation ("it logs instead of doing")
- TODO, FIXME, XXX, HACK, STUB comments indicating unfinished work
- Commented-out code blocks (dead code the implementer was too lazy to remove or replace)
- Copy-pasted boilerplate that wasn't adapted (generic variable names, template comments still present)
- Error handling that swallows exceptions silently (catch {} / except: pass)
- Functions that always return the same thing regardless of input
- "Mock" or "fake" or "dummy" data used as the real implementation
- Type assertions / type casts used to paper over actual type errors (as any, type: ignore)
- Circular imports or missing imports that would crash at runtime
- SQL/NoSQL queries built with string concatenation (injection vulnerability)
- Secrets, API keys, passwords hardcoded in source files
- File or network operations with no error handling at all

SMELL CHECKS (multiple smells = FAIL):
- Functions over 100 lines with no decomposition
- Deeply nested conditionals (4+ levels)
- Variables named temp, data, result, thing, stuff, x, val with no context
- Boolean parameters that change function behavior (flag arguments)
- Magic numbers/strings with no constants or explanation
- Duplicated logic across files (copy-paste coding)
- API endpoints with no input validation
- State mutations in supposedly pure functions
- Race conditions in concurrent code (shared mutable state with no locks)
- Missing edge cases: null/undefined inputs, empty arrays, boundary values
- Tests that test the framework rather than the business logic
- Tests with no assertions or with assertions that always pass (expect(true).toBe(true))
- Tests that mock so much they test nothing real
- Frontend components with inline styles that should be themed
- Frontend components with no loading states, no error states, no empty states
- Accessibility violations: missing alt text, no keyboard navigation, no ARIA labels
- API responses with no consistent error format

WIRING CHECKS:
- Verify ALL must_haves key_links: if A should connect to B, trace the actual import/call chain
- Check that API routes are actually registered in the router (not just defined as functions)
- Check that database models are actually used by the API (not just defined)
- Check that frontend components actually call the API endpoints (not just render static data)
- Check that environment variables are actually read (not just documented)

═══════════════════════════════════════════════════════════════
STEP 2: RUN QUANTITATIVE TESTS
═══════════════════════════════════════════════════════════════

cd $PROJECT_DIR && $TEST_COMMAND

If tests fail, stop here — FAIL. Do NOT proceed.

If tests pass, ask yourself: are these tests actually testing anything meaningful?
Grep through the test files and check:
- Do assertions test actual business logic or just structural boilerplate?
- Are there tests for error paths, not just happy paths?
- Do tests use realistic inputs or trivial ones (test("", 0, []))?

═══════════════════════════════════════════════════════════════
STEP 3: PLAYWRIGHT VISUAL VERIFICATION
═══════════════════════════════════════════════════════════════

a. Navigate to ${DEV_SERVER_URL}${QUAL_URL} using browser_navigate
b. Take a snapshot using browser_snapshot
c. Choose your own test inputs — use REALISTIC, UNPREDICTABLE values
   (not "test", "foo", "123" — use real names, real emails, edge cases)
d. For each qualitative criterion, interact with the UI:
   browser_click, browser_type, browser_fill_form as needed
e. Take screenshots at each step using browser_take_screenshot
f. Check browser_console_messages for errors (warnings are OK, errors are NOT)
g. Critically assess every screenshot:
   - Broken layouts, overlapping elements, cut-off text = FAIL
   - Placeholder text still visible ("Lorem ipsum", "TODO", "Coming soon") = FAIL
   - Missing error states (submit empty form — does it just silently fail?) = FAIL
   - Missing loading states (click submit — does the UI freeze with no feedback?) = FAIL
   - Console errors (unhandled promise rejections, 404s, CORS errors) = FAIL
   - Buttons that do nothing when clicked = FAIL
   - Forms that accept obviously invalid input without feedback = FAIL
h. Try to BREAK the UI:
   - Submit empty forms
   - Enter extremely long text
   - Click buttons rapidly
   - Navigate away and back
   - Check if state persists correctly

═══════════════════════════════════════════════════════════════
STEP 4: VERDICT
═══════════════════════════════════════════════════════════════

Only if ALL of the following are true:
- Zero hard fails from Step 1
- No more than 2 minor smells from Step 1
- All must_haves verified (truths hold, artifacts exist, key_links wired)
- Tests pass AND test quality is acceptable
- Visual verification passes with no broken states
- You would stake your professional reputation on this code being production-ready

NOTE: After your verdict, the orchestrator may run an additional formal verification gate
(Prusti/Kani/semver/CrossHair) via the run_verification() MCP tool, depending on the plan's
verification_level setting. You do not need to invoke these tools — they run as a separate
orchestrator-driven gate between your PASS verdict and GK token submission.

Then run: cd $PROJECT_DIR && bash $FETCH_SCRIPT --session-dir ${SESSION_DIR}

OUTPUT: your entire response is one of:
<verification-complete>
PASS: [paste the token from the fetch script here]
</verification-complete>
or
<verification-complete>
FAIL
[List every issue found. Be specific: file path, line, what's wrong, why it matters.]
</verification-complete>

If you FAIL, the issues list is critical — the executor needs to know exactly what to fix.
PLANEOF

echo "Verifier prompt generated at: ${SESSION_DIR}/verifier-prompt.local.md" >&2
