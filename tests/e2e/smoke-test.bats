#!/usr/bin/env bats
# End-to-End Smoke Test for GSD-VGL
#
# Verifies: plan validation, task dispatch, state transitions, and completion token.
# Uses tests/fixtures/sample-project/ as the base fixture.
# Each test gets its own temp copy to avoid cross-contamination.

FIXTURE_DIR=""
SCRIPTS_DIR=""

setup_file() {
    # Resolve paths
    BATS_TEST_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
    PROJECT_ROOT="$(cd "$BATS_TEST_DIR/../.." && pwd)"
    export FIXTURE_DIR="$PROJECT_ROOT/tests/fixtures/sample-project"
    export SCRIPTS_DIR="$PROJECT_ROOT/scripts"

    # Load bats libraries
    BATS_LIB_DIR="$PROJECT_ROOT/node_modules"
    load "$BATS_LIB_DIR/bats-support/load.bash"
    load "$BATS_LIB_DIR/bats-assert/load.bash"
    load "$BATS_LIB_DIR/bats-file/load.bash"
}

setup() {
    # Resolve paths fresh for each test (bats doesn't share across setup_file)
    BATS_TEST_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
    PROJECT_ROOT="$(cd "$BATS_TEST_DIR/../.." && pwd)"
    FIXTURE_DIR="$PROJECT_ROOT/tests/fixtures/sample-project"
    SCRIPTS_DIR="$PROJECT_ROOT/scripts"

    # Load bats libraries
    BATS_LIB_DIR="$PROJECT_ROOT/node_modules"
    load "$BATS_LIB_DIR/bats-support/load.bash"
    load "$BATS_LIB_DIR/bats-assert/load.bash"
    load "$BATS_LIB_DIR/bats-file/load.bash"

    # Create a temp copy of the fixture for this test
    TEST_DIR="$(mktemp -d)"
    cp -r "$FIXTURE_DIR/." "$TEST_DIR/"

    # Test token for VGL completion gating
    TEST_TOKEN="VGL_COMPLETE_00000000000000000000000000000000"
    echo "$TEST_TOKEN" > "$TEST_DIR/.claude/verifier-token.secret"
}

teardown() {
    if [[ -n "${TEST_DIR:-}" ]] && [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# -------------------------------------------------------------------
# Test 1: Validate the fixture plan
# -------------------------------------------------------------------
@test "e2e: validate fixture plan exits 0" {
    run python3 "$SCRIPTS_DIR/validate-plan.py" "$TEST_DIR/.claude/plan/plan.yaml"
    assert_success
    assert_output --partial "Validation PASSED"
}

# -------------------------------------------------------------------
# Test 2: next-task finds task 1.1 as the first unblocked task
# -------------------------------------------------------------------
@test "e2e: next-task returns task 1.1 as first unblocked" {
    run python3 "$SCRIPTS_DIR/next-task.py" "$TEST_DIR/.claude/plan/plan.yaml"
    assert_success
    # Output should be JSON with id "1.1"
    echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['id']=='1.1', f'Expected 1.1, got {d[\"id\"]}'"
}

# -------------------------------------------------------------------
# Test 3: After completing 1.1 via transition, next task is 1.2
# -------------------------------------------------------------------
@test "e2e: transition after completing 1.1 finds task 1.2" {
    # State file says task_id: 1.1 -- transition-task.sh will complete 1.1 and find 1.2
    cd "$TEST_DIR"
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success
    # stdout should be JSON containing task 1.2
    echo "$output" | grep -q '"1.2"'
}

# -------------------------------------------------------------------
# Test 4: fetch-completion-token reveals token on passing tests
# -------------------------------------------------------------------
@test "e2e: fetch-completion-token reveals token on passing tests" {
    # Set up a session directory with the required files
    SESSION_DIR="$TEST_DIR/.claude/vgl-sessions/task-1.1"
    mkdir -p "$SESSION_DIR"

    # Create verifier-loop.local.md in session dir
    cat > "$SESSION_DIR/verifier-loop.local.md" <<'EOF'
---
session_id: "smoke-test-session-001"
task_id: "1.1"
iteration: 1
max_iterations: 5
project_dir: "."
---

# Verifier Loop State
Active session for smoke testing.
EOF

    # Create verifier-token.secret with a passing test command
    TEST_CMD="echo pass"
    B64=$(echo -n "$TEST_CMD" | base64)
    HASH=$(echo -n "$TEST_CMD" | sha256sum | cut -d' ' -f1)
    cat > "$SESSION_DIR/verifier-token.secret" <<TOKENEOF
smoke-test-token-xyz789
TEST_CMD_B64:${B64}
TEST_CMD_HASH:${HASH}
TOKENEOF
    chmod 600 "$SESSION_DIR/verifier-token.secret"

    cd "$TEST_DIR"
    run "$SCRIPTS_DIR/fetch-completion-token.sh" --session-dir ".claude/vgl-sessions/task-1.1"
    assert_success
    # Token should be revealed
    echo "$output" | grep -q "smoke-test-token-xyz789"
    echo "$output" | grep -q "token-granted"
}

# -------------------------------------------------------------------
# Test 5: After completing all tasks, transition exits 2
# -------------------------------------------------------------------
@test "e2e: all tasks complete causes transition exit 2" {
    # First complete task 1.1 (state file has task_id: 1.1)
    cd "$TEST_DIR"
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    # Now update state file to point to task 1.2
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<'EOF'
---
session_id: "smoke-test-session-001"
task_id: "1.2"
iteration: 1
max_iterations: 5
started_at: "2026-01-01T00:00:00Z"
project_dir: "."
---

# Verifier Loop State
Active session for smoke testing - task 1.2.
EOF

    # Now complete task 1.2 -- no more tasks should remain
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_failure
    [ "$status" -eq 2 ]
}
