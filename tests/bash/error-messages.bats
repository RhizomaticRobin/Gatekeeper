#!/usr/bin/env bats
# error-messages.bats — tests for standardized error messages across scripts and hooks
#
# Task 5.2: Error Message Audit and Improvement
# Verifies:
#   - All error paths use "Error: <description>" format
#   - All error paths include "Try: <recovery action>" suggestions
#   - guard-skills block message lists available alternatives
#   - stop-hook corruption messages include cleanup instructions
#   - Consistent format across all scripts and hooks

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    mkdir -p "$TEST_DIR/.claude/plan/tasks"
    cd "$TEST_DIR"
}

teardown() {
    cd /
    if [[ -n "${TEST_DIR:-}" ]] && [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# =============================================================================
# Test 1: transition-task missing plan — error includes "Try:" suggestion
# =============================================================================
@test "transition-task missing plan — error includes Try suggestion" {
    # Create state file but no plan file
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<'EOF'
---
session_id: "test-session"
task_id: "1.1"
iteration: 1
max_iterations: 5
project_dir: "/tmp/test"
---
EOF
    # No plan file exists
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_failure
    [ "$status" -eq 1 ]
    # Must have "Error:" prefix
    echo "$output" | grep -q "Error:"
    # Must have "Try:" recovery suggestion
    echo "$output" | grep -q "Try:"
}

# =============================================================================
# Test 2: transition-task missing state — error includes "Try:" suggestion
# =============================================================================
@test "transition-task missing state — error includes Try suggestion" {
    # Create plan but no state file
    cat > "$TEST_DIR/.claude/plan/plan.yaml" <<'YAML'
metadata:
  project: "test-project"
  dev_server_command: "echo ok"
  dev_server_url: "http://localhost:3000"
  model_profile: "default"
phases:
  - id: 1
    name: "Phase 1"
    tasks:
      - id: "1.1"
        name: "Task A"
        status: "pending"
        depends_on: []
        deliverables:
          backend: "test"
          frontend: "test"
        tests:
          quantitative:
            command: "echo pass"
          qualitative:
            criteria:
              - "works"
        prompt_file: "tasks/task-1.1.md"
YAML
    # No state file exists
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_failure
    [ "$status" -eq 1 ]
    # Must have "Error:" prefix
    echo "$output" | grep -q "Error:"
    # Must have "Try:" recovery suggestion
    echo "$output" | grep -q "Try:"
}

# =============================================================================
# Test 3: fetch-token missing state — error includes "Try:" suggestion
# =============================================================================
@test "fetch-token missing state — error includes Try suggestion" {
    # No state file exists
    run "$SCRIPTS_DIR/fetch-completion-token.sh"
    assert_failure
    [ "$status" -eq 1 ]
    # Must have "Error:" prefix
    echo "$output" | grep -q "Error:"
    # Must have "Try:" recovery suggestion
    echo "$output" | grep -q "Try:"
}

# =============================================================================
# Test 4: fetch-token missing token file — error includes "Try:" suggestion
# =============================================================================
@test "fetch-token missing token file — error includes Try suggestion" {
    # Create state file but no token file
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<'EOF'
---
session_id: "test-session"
task_id: "1.1"
iteration: 1
max_iterations: 5
project_dir: "."
---
EOF
    run "$SCRIPTS_DIR/fetch-completion-token.sh"
    assert_failure
    [ "$status" -eq 1 ]
    # Must have "Error:" prefix
    echo "$output" | grep -q "Error:"
    # Must have "Try:" recovery suggestion
    echo "$output" | grep -q "Try:"
}

# =============================================================================
# Test 5: guard-skills block message — includes available alternatives
# =============================================================================
@test "guard-skills block message — includes available alternatives" {
    HOOK="$HOOKS_DIR/guard-skills.sh"
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gsd-vgl:quest"}}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_failure 2
    # Must mention BLOCKED
    echo "$output" | grep -q "BLOCKED"
    # Must list available alternatives: /cross-team and /progress
    echo "$output" | grep -q "/cross-team"
    echo "$output" | grep -q "/progress"
}

# =============================================================================
# Test 6: stop-hook corruption — error includes cleanup instructions
# =============================================================================
@test "stop-hook corruption — error includes cleanup instructions" {
    HOOK="$HOOKS_DIR/stop-hook.sh"
    # Create an empty state file (triggers corruption path)
    touch "$TEST_DIR/.claude/verifier-loop.local.md"
    local token="VGL_COMPLETE_0000000000000000ab54a98ceb1f0ad2"
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"

    run bash -c 'echo '"'"'{"transcript_path":"/dev/null"}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_success
    # Must mention corruption/cleanup
    echo "$output" | grep -qi "corrupt"
    # Must include recovery instructions mentioning /run-away or cleanup steps
    echo "$output" | grep -q "run-away"
}

# =============================================================================
# Test 7: stop-hook missing session_id — error includes cleanup instructions
# =============================================================================
@test "stop-hook missing session_id — error includes cleanup instructions" {
    HOOK="$HOOKS_DIR/stop-hook.sh"
    # Create a state file without session_id
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<EOF
---
iteration: 1
max_iterations: 5
project_dir: "${TEST_DIR}"
---

Prompt text without session_id.
EOF
    local token="VGL_COMPLETE_0000000000000000ab54a98ceb1f0ad2"
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"

    run bash -c 'echo '"'"'{"transcript_path":"/dev/null"}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_success
    # Must mention corruption
    echo "$output" | grep -qi "corrupt"
    # Must include recovery instructions
    echo "$output" | grep -q "run-away"
}

# =============================================================================
# Test 8: consistent format — transition-task errors use "Error:" pattern
# =============================================================================
@test "consistent format — transition-task error paths use Error: prefix" {
    # Check that all echo statements with error messages in transition-task.sh
    # that exit with code 1 use the "Error:" prefix format.
    # We use a two-line window: find echo lines immediately before "exit 1"
    # and verify each contains "Error:"
    run bash -c '
        FAIL=0
        while IFS= read -r line; do
            if ! echo "$line" | grep -qi "Error:"; then
                echo "Missing Error: prefix in: $line"
                FAIL=1
            fi
        done < <(grep -B2 "exit 1" "'"$SCRIPTS_DIR"'/transition-task.sh" | grep "echo.*Error\\|echo.*error\\|echo.*ERROR" || grep -B2 "exit 1" "'"$SCRIPTS_DIR"'/transition-task.sh" | grep "echo" | grep -v "^--$")
        exit $FAIL
    '
    # Alternative simpler check: every "exit 1" block in the script must
    # have an echo with "Error:" within 2 lines before it
    ERROR_ECHO_COUNT=$(grep -c "Error:" "$SCRIPTS_DIR/transition-task.sh" || true)
    EXIT1_COUNT=$(grep -c "exit 1" "$SCRIPTS_DIR/transition-task.sh" || true)
    # There should be at least as many Error: lines as exit 1 lines
    [ "$ERROR_ECHO_COUNT" -ge "$EXIT1_COUNT" ]
}

# =============================================================================
# Test 9: consistent format — fetch-completion-token errors use "Error:" pattern
# =============================================================================
@test "consistent format — fetch-completion-token error paths use Error: prefix" {
    # Count Error: prefixed messages vs exit 1 paths
    # Every exit 1 should have an associated Error: message
    ERROR_ECHO_COUNT=$(grep -c "Error:" "$SCRIPTS_DIR/fetch-completion-token.sh" || true)
    EXIT1_COUNT=$(grep -c "exit 1" "$SCRIPTS_DIR/fetch-completion-token.sh" || true)
    # There should be at least as many Error: lines as exit 1 lines
    [ "$ERROR_ECHO_COUNT" -ge "$EXIT1_COUNT" ]
}

# =============================================================================
# Test 10: fetch-token integrity failure — includes "Try:" suggestion
# =============================================================================
@test "fetch-token integrity failure — includes Try suggestion" {
    # Create state file
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<'EOF'
---
session_id: "test-session"
task_id: "1.1"
iteration: 1
max_iterations: 5
project_dir: "."
---
EOF
    # Create token file with wrong hash
    TEST_CMD="echo pass"
    B64=$(echo -n "$TEST_CMD" | base64)
    WRONG_HASH="0000000000000000000000000000000000000000000000000000000000000000"
    cat > "$TEST_DIR/.claude/verifier-token.secret" <<TOKENEOF
test-token-abc123
TEST_CMD_B64:${B64}
TEST_CMD_HASH:${WRONG_HASH}
TOKENEOF
    chmod 600 "$TEST_DIR/.claude/verifier-token.secret"
    run "$SCRIPTS_DIR/fetch-completion-token.sh"
    assert_failure
    [ "$status" -eq 1 ]
    # Must have "Error:" prefix
    echo "$output" | grep -q "Error:"
    # Must have "Try:" recovery suggestion
    echo "$output" | grep -q "Try:"
}

# =============================================================================
# Test 11: transition-task missing task_id — error includes "Try:" suggestion
# =============================================================================
@test "transition-task missing task_id — error includes Try suggestion" {
    # Create plan
    cat > "$TEST_DIR/.claude/plan/plan.yaml" <<'YAML'
metadata:
  project: "test-project"
  dev_server_command: "echo ok"
  dev_server_url: "http://localhost:3000"
  model_profile: "default"
phases:
  - id: 1
    name: "Phase 1"
    tasks:
      - id: "1.1"
        name: "Task A"
        status: "pending"
        depends_on: []
        deliverables:
          backend: "test"
          frontend: "test"
        tests:
          quantitative:
            command: "echo pass"
          qualitative:
            criteria:
              - "works"
        prompt_file: "tasks/task-1.1.md"
YAML
    # State file without task_id
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<'EOF'
---
session_id: "test-session"
iteration: 1
max_iterations: 5
project_dir: "/tmp/test"
---
EOF
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_failure
    [ "$status" -eq 1 ]
    # Must have "Error:" prefix
    echo "$output" | grep -q "Error:"
    # Must have "Try:" recovery suggestion
    echo "$output" | grep -q "Try:"
}
