#!/usr/bin/env bats
# Tests for scripts/fetch-completion-token.sh

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    mkdir -p "$TEST_DIR/.claude"

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

    # Default: test command that passes
    TEST_CMD="echo pass"
    B64=$(echo -n "$TEST_CMD" | base64)
    HASH=$(echo -n "$TEST_CMD" | sha256sum | cut -d' ' -f1)
    cat > "$TEST_DIR/.claude/verifier-token.secret" <<TOKENEOF
test-token-abc123
TEST_CMD_B64:${B64}
TEST_CMD_HASH:${HASH}
TOKENEOF
    chmod 600 "$TEST_DIR/.claude/verifier-token.secret"
    cd "$TEST_DIR"
}

teardown() {
    cd /
    rm -rf "$TEST_DIR"
}

@test "token granted when test command passes" {
    run "$SCRIPTS_DIR/fetch-completion-token.sh"
    assert_success
    echo "$output" | grep -q "test-token-abc123"
    echo "$output" | grep -q "token-granted"
}

@test "token denied when test command fails" {
    # Replace token file with a failing test command
    FAIL_CMD="false"
    B64=$(echo -n "$FAIL_CMD" | base64)
    HASH=$(echo -n "$FAIL_CMD" | sha256sum | cut -d' ' -f1)
    cat > "$TEST_DIR/.claude/verifier-token.secret" <<TOKENEOF
test-token-abc123
TEST_CMD_B64:${B64}
TEST_CMD_HASH:${HASH}
TOKENEOF
    chmod 600 "$TEST_DIR/.claude/verifier-token.secret"
    run "$SCRIPTS_DIR/fetch-completion-token.sh"
    assert_failure
    echo "$output" | grep -q "TESTS_FAILED"
}

@test "integrity check failure on wrong hash exits 1" {
    # Tamper with the hash
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
    echo "$output" | grep -qi "integrity"
}

@test "missing state file exits 1" {
    rm "$TEST_DIR/.claude/verifier-loop.local.md"
    run "$SCRIPTS_DIR/fetch-completion-token.sh"
    assert_failure
    [ "$status" -eq 1 ]
}

@test "missing token file exits 1" {
    rm "$TEST_DIR/.claude/verifier-token.secret"
    run "$SCRIPTS_DIR/fetch-completion-token.sh"
    assert_failure
    [ "$status" -eq 1 ]
}
