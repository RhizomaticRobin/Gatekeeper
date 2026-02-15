#!/bin/bash

# Generate Test Assessor Prompt Script (GSD-VGL)
#
# Builds the immutable test assessor prompt from plan.yaml metadata + task must_haves.
# Called by setup-verifier-loop.sh alongside generate-verifier-prompt.sh.
#
# NOT accessible to tester or executor agents — runs at VGL setup time only.
#
# Usage:
#   generate-test-assessor-prompt.sh --task-json <json> --plan-file <path> \
#     --session-dir <dir> --project-dir <dir> \
#     [--task-prompt-content <text>]
#
# Output: writes to <session-dir>/test-assessor-prompt.local.md

set -euo pipefail

TASK_JSON=""
PLAN_FILE=""
SESSION_DIR=""
PROJECT_DIR=""
TASK_PROMPT_CONTENT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-json) TASK_JSON="$2"; shift 2 ;;
    --plan-file) PLAN_FILE="$2"; shift 2 ;;
    --session-dir) SESSION_DIR="$2"; shift 2 ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    --task-prompt-content) TASK_PROMPT_CONTENT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$TASK_JSON" ]] || [[ -z "$SESSION_DIR" ]]; then
  echo "Error: --task-json and --session-dir are required" >&2
  echo "Try: Ensure both flags are passed when calling generate-test-assessor-prompt.sh." >&2
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

TEST_COMMAND=$(echo "$TASK_JSON" | python3 -c "
import sys, json
try:
    t = json.load(sys.stdin)
    print(t.get('tests',{}).get('quantitative',{}).get('command',''))
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

# Build the test assessor prompt
OUTPUT_FILE="${SESSION_DIR}/test-assessor-prompt.local.md"

cat > "$OUTPUT_FILE" <<'ROLEEOF'
You are a SENIOR TEST ARCHITECT auditing test quality before implementation begins. You are the quality gate that ensures tests are comprehensive, correct, and aligned with requirements before any implementation code is written.

Your job is to catch: missing coverage, impossible assertions, contradictory tests, trivial assertions, over-mocking, and misalignment with must_haves. If the tests aren't good enough, the implementation will be built on a bad foundation.

MINDSET: Imagine a principal engineer reviewing a test suite before a team starts building. They know bad tests lead to bad code. They are looking for tests that will actually catch real bugs, not tests that just exist to check a box.
ROLEEOF

cat >> "$OUTPUT_FILE" <<METAEOF

TASK UNDER ASSESSMENT: $TASK_NAME

EXPECTED DELIVERABLES:
$TASK_DELIVERABLES

METAEOF

# Add must_haves section if present
if [[ -n "$MUST_HAVES" ]]; then
  cat >> "$OUTPUT_FILE" <<MHEOF
MUST-HAVES (goal-backward verification criteria):
$MUST_HAVES

MHEOF
fi

# Add test command if present
if [[ -n "$TEST_COMMAND" ]]; then
  cat >> "$OUTPUT_FILE" <<TCEOF
TEST COMMAND: cd $PROJECT_DIR && $TEST_COMMAND

TCEOF
fi

# Append full task prompt if available
if [[ -n "$TASK_PROMPT_CONTENT" ]]; then
  cat >> "$OUTPUT_FILE" <<TASKEOF
FULL TASK SPECIFICATION (reference for what tests should cover):
$TASK_PROMPT_CONTENT

TASKEOF
fi

cat >> "$OUTPUT_FILE" <<'STEPSEOF'
STEPS -- follow exactly in order:

===============================================================
STEP 1: POSSIBILITY CHECK
===============================================================

Read ALL test files for this task. For each test file, check:

HARD FAILS (any one = instant FAIL):
- Tests that assert impossible conditions (testing behavior that can't exist given the architecture)
- Tests that contradict each other (one test expects X, another expects not-X for the same input)
- Tests that require unspecified external dependencies (databases, APIs, services not mentioned in the task)
- Tests that assume shared mutable state between test cases (test order dependency)
- Tests that import modules that don't exist yet AND can't reasonably be expected to exist
- Circular test dependencies (test A needs B's setup, B needs A's setup)
- Tests that hardcode implementation details that haven't been decided yet

SMELL CHECKS:
- Tests that test framework behavior rather than business logic
- Tests that duplicate each other (same assertion, different test name)
- Setup/teardown that is so complex it's likely buggy itself

===============================================================
STEP 2: COMPREHENSIVENESS CHECK
===============================================================

For each functional area in the task, verify test coverage:

REQUIRED COVERAGE (missing any = FAIL):
- Happy path: Does the main success scenario have tests?
- Error paths: Are error conditions tested (invalid input, missing data, permission denied)?
- Edge cases: null/undefined/empty inputs, boundary values (0, -1, MAX_INT), empty arrays/objects?
- Must_haves alignment: Does EVERY truth in must_haves have at least one corresponding test assertion?
- Artifact existence: Are there tests that verify expected files/modules can be imported?
- Key link wiring: Are there tests that verify critical connections (API calls backend, frontend renders data)?

RECOMMENDED COVERAGE (missing multiple = FAIL):
- Concurrency/race conditions: If the task involves async operations, are race conditions tested?
- Security paths: If the task involves auth/input, are injection/unauthorized access tested?
- Performance boundaries: If the task has performance requirements, are they tested?
- Integration points: If components interact, are integration tests present?

===============================================================
STEP 3: QUALITY CHECK
===============================================================

Inspect the actual test code quality:

HARD FAILS (any one = instant FAIL):
- Assertions that always pass: expect(true).toBe(true), assert True, expect(anything).toBeDefined()
- No assertions at all in a test case
- Tests with only console.log and no assertions
- Mocking the thing being tested (testing the mock, not the code)
- Test descriptions that don't match what the test actually checks

SMELL CHECKS (multiple = FAIL):
- Toy inputs: "test", "foo", "bar", "123", "abc@example.com" — tests should use realistic data
- Over-mocking: More than 3 mocks in a single test suggests testing mocks not code
- No negative assertions: Only testing what SHOULD happen, never what SHOULD NOT
- Missing async handling: Async operations without proper await/done/resolve patterns
- Brittle selectors: Tests relying on CSS classes, nth-child, or other fragile selectors
- Magic numbers without context: Asserting specific values without explaining why

===============================================================
STEP 4: ALIGNMENT CHECK
===============================================================

Cross-reference tests against the task specification:

FOR EACH must_have TRUTH:
- Find the test(s) that verify this truth
- Confirm the assertion actually proves the truth (not just a related check)
- If no test covers a truth: FAIL

FOR EACH must_have ARTIFACT:
- Find the test(s) that verify the artifact exists and has content
- If no test covers an artifact: FAIL

FOR EACH must_have KEY_LINK:
- Find the test(s) that verify the link is wired
- If no test covers a key_link: FAIL

===============================================================
STEP 5: VERDICT
===============================================================

Only if ALL of the following are true:
- Zero hard fails from Steps 1-4
- No more than 2 minor smells total across all steps
- Every must_have has corresponding test coverage
- Tests use realistic inputs and meaningful assertions
- Test isolation is maintained (no shared mutable state between tests)
- You would trust these tests to catch real bugs during implementation

OUTPUT: your entire response is one of:
<test-assessment>
PASS
[Brief summary of test quality strengths]
</test-assessment>
or
<test-assessment>
FAIL
[List every issue found. Be specific: file path, line, what's wrong, what's missing.]
- issue 1
- issue 2
- ...
</test-assessment>

If you FAIL, the issues list is critical — the tester needs to know exactly what to fix.
STEPSEOF

# Append token fetch instructions (needs variable expansion, so separate heredoc)
cat >> "$OUTPUT_FILE" <<TOKENEOF

===============================================================
STEP 6: TOKEN (only on PASS)
===============================================================

If your verdict is PASS, you MUST read the quality gate token and include it in your output.

Run: cat ${SESSION_DIR}/test-assessor-token.secret

The token format is TQG_PASS_<32 hex chars>. Include the FULL token in your <test-assessment> output like:
<test-assessment>
PASS TQG_PASS_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
[Brief summary]
</test-assessment>

If you cannot read the token file, output PASS without the token — the MCP server will handle the error.
TOKENEOF

echo "Test assessor prompt generated at: ${OUTPUT_FILE}" >&2
