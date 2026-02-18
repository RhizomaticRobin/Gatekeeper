#!/bin/bash

# Fetch Completion Token Script (GSD-VGL)
# This script ONLY reveals the completion token if independent verification passes
# The Verifier subagent calls this - it never has the token in its prompt
#
# Security model:
# 1. Token AND test command are stored in .claude/verifier-token.secret
# 2. Test command is base64-encoded with SHA-256 integrity hash
# 3. This script reads the test command from the SECRET file, NOT the state file
# 4. Even if an agent edits the state file, the fetch script uses the original test command
# 5. Token is ONLY output if tests pass

set -euo pipefail

SESSION_DIR=".claude"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-dir) SESSION_DIR="$2"; shift 2 ;;
    *) shift ;;
  esac
done
STATE_FILE="${SESSION_DIR}/verifier-loop.local.md"
TOKEN_FILE="${SESSION_DIR}/verifier-token.secret"

# Check state file exists
if [[ ! -f "$STATE_FILE" ]]; then
  echo "Error: No active VGL session found at ${STATE_FILE}"
  echo "Try: Run /gatekeeper:cross-team to start a new VGL session, or check that the session directory is correct."
  exit 1
fi

# Check token file exists (created by setup, only this script should read it)
if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Error: Token file not found at ${TOKEN_FILE} - VGL session may be corrupted"
  echo "Try: Run /gatekeeper:run-away to reset the session, then restart with /gatekeeper:cross-team."
  exit 1
fi

# Parse state file for session info
FRONTMATTER=$(awk 'NR==1 && /^---$/{next} /^---$/{exit} NR>1{print}' "$STATE_FILE")
SESSION_ID=$(echo "$FRONTMATTER" | grep '^session_id:' | sed 's/session_id: *//' | sed 's/^"\(.*\)"$/\1/')
PROJECT_DIR=$(echo "$FRONTMATTER" | grep '^project_dir:' | sed 's/project_dir: *//' | sed 's/^"\(.*\)"$/\1/')

# Read test command from TOKEN FILE (tamper-proof, NOT from state file)
TOKEN_FILE_CONTENT=$(cat "$TOKEN_FILE")
STORED_B64=$(echo "$TOKEN_FILE_CONTENT" | grep '^TEST_CMD_B64:' | sed 's/^TEST_CMD_B64://')
STORED_HASH=$(echo "$TOKEN_FILE_CONTENT" | grep '^TEST_CMD_HASH:' | sed 's/^TEST_CMD_HASH://')

if [[ -z "$STORED_B64" ]] || [[ -z "$STORED_HASH" ]]; then
  echo "Error: Token file missing test command data - session may be corrupted"
  echo "Try: Run /gatekeeper:run-away to reset the session, then restart with /gatekeeper:cross-team."
  exit 1
fi

# Decode and verify integrity
TEST_COMMAND=$(echo "$STORED_B64" | base64 -d)
COMPUTED_HASH=$(echo -n "$TEST_COMMAND" | sha256sum | cut -d' ' -f1)

if [[ "$COMPUTED_HASH" != "$STORED_HASH" ]]; then
  echo "Error: Test command integrity check FAILED - token file may have been tampered with"
  echo "  Expected hash: $STORED_HASH"
  echo "  Computed hash: $COMPUTED_HASH"
  echo "Try: Run /gatekeeper:run-away to reset the session, then restart with /gatekeeper:cross-team."
  exit 1
fi

echo "Test command integrity verified (SHA-256 match)"

# Change to project directory if specified
if [[ -n "$PROJECT_DIR" ]] && [[ -d "$PROJECT_DIR" ]]; then
  cd "$PROJECT_DIR"
fi

echo "═══════════════════════════════════════════════════════════════════════════════════════"
echo "                    INDEPENDENT VERIFICATION IN PROGRESS"
echo "═══════════════════════════════════════════════════════════════════════════════════════"
echo ""
echo "Session: $SESSION_ID"
echo "Project: $(pwd)"
echo "Test command: $TEST_COMMAND"
echo ""
echo "This script runs tests INDEPENDENTLY of the Verifier's claims."
echo "Token will ONLY be revealed if tests pass."
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════════════"
echo ""

# Run the test command and capture output + exit code
echo "Running: $TEST_COMMAND"
echo ""

TEST_OUTPUT=$(eval "$TEST_COMMAND" 2>&1) || TEST_EXIT_CODE=$?
TEST_EXIT_CODE=${TEST_EXIT_CODE:-0}

echo "$TEST_OUTPUT"
echo ""

# Check if tests passed
if [[ $TEST_EXIT_CODE -ne 0 ]]; then
  echo "═══════════════════════════════════════════════════════════════════════════════════════"
  echo "                         VERIFICATION FAILED - TOKEN DENIED"
  echo "═══════════════════════════════════════════════════════════════════════════════════════"
  echo ""
  echo "Error: Tests failed with exit code: $TEST_EXIT_CODE"
  echo ""
  echo "The completion token will NOT be revealed."
  echo "Try: Fix the failing tests and run the test command again."
  echo ""
  echo "<token-denied>"
  echo "TESTS_FAILED"
  echo "Exit code: $TEST_EXIT_CODE"
  echo "</token-denied>"
  exit 1
fi

# Additional checks (basic sanity)
ISSUES=""

# Check for TODO/FIXME in source files (if src/ exists)
if [[ -d "src" ]]; then
  TODO_COUNT=$(timeout 10 grep -r -I -i "TODO\|FIXME\|XXX\|HACK" src/ 2>&1 | wc -l | tr -d ' ') || {
    echo "WARN: TODO/FIXME scan failed — skipping this check" >&2
    TODO_COUNT="0"
  }
  if [[ "$TODO_COUNT" =~ ^[0-9]+$ ]] && [[ "$TODO_COUNT" -gt 0 ]]; then
    ISSUES="${ISSUES}Found $TODO_COUNT TODO/FIXME comments in src/\n"
  fi
fi

# Check for stub implementations
if [[ -d "src" ]]; then
  STUB_COUNT=$(timeout 10 grep -r -I "pass  # TODO\|raise NotImplementedError\|return None  # stub" src/ 2>&1 | wc -l | tr -d ' ') || {
    echo "WARN: Stub implementation scan failed — skipping this check" >&2
    STUB_COUNT="0"
  }
  if [[ "$STUB_COUNT" =~ ^[0-9]+$ ]] && [[ "$STUB_COUNT" -gt 0 ]]; then
    ISSUES="${ISSUES}Found $STUB_COUNT stub implementations in src/\n"
  fi
fi

# If issues found, deny token
if [[ -n "$ISSUES" ]]; then
  echo "═══════════════════════════════════════════════════════════════════════════════════════"
  echo "                         VERIFICATION FAILED - TOKEN DENIED"
  echo "═══════════════════════════════════════════════════════════════════════════════════════"
  echo ""
  echo "Error: Tests passed but additional checks failed:"
  echo -e "$ISSUES"
  echo ""
  echo "The completion token will NOT be revealed."
  echo "Try: Address the issues above (remove TODOs, replace stubs with real implementations) and retry."
  echo ""
  echo "<token-denied>"
  echo "ADDITIONAL_CHECKS_FAILED"
  echo -e "$ISSUES"
  echo "</token-denied>"
  exit 1
fi

# All checks passed - reveal the token (line 1 of token file)
COMPLETION_TOKEN=$(head -1 "$TOKEN_FILE")
if [[ -z "$COMPLETION_TOKEN" ]] || [[ "$COMPLETION_TOKEN" == "PLACEHOLDER_TOKEN_GENERATED_AT_CALL_TIME" ]]; then
  echo "Error: Token file is empty or contains placeholder — VGL token was never generated"
  echo "Try: Run /gatekeeper:run-away to reset the session, then restart with /gatekeeper:cross-team."
  exit 1
fi

echo "═══════════════════════════════════════════════════════════════════════════════════════"
echo "                         VERIFICATION PASSED - TOKEN GRANTED"
echo "═══════════════════════════════════════════════════════════════════════════════════════"
echo ""
echo "All tests passed. All checks passed."
echo ""
echo "To complete the loop, output EXACTLY:"
echo ""
echo "<verification-complete>"
echo "$COMPLETION_TOKEN"
echo "</verification-complete>"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════════════"

echo ""
echo "<token-granted>"
echo "$COMPLETION_TOKEN"
echo "</token-granted>"
