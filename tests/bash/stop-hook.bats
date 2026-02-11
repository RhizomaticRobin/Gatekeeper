#!/usr/bin/env bats
# stop-hook.bats — tests for hooks/stop-hook.sh
# Verifies VGL loop controller behavior: passthrough, iteration, token matching.

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    HOOK="$HOOKS_DIR/stop-hook.sh"
    mkdir -p "$TEST_DIR/.claude"
    cd "$TEST_DIR"
}

teardown() {
    if [[ -n "${TEST_DIR:-}" ]] && [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# Helper: generate a valid token (32 hex chars)
make_token() {
    echo "VGL_COMPLETE_0000000000000000ab54a98ceb1f0ad2"
}

# Helper: create a valid state file with given iteration and max
create_state() {
    local iteration="${1:-1}"
    local max_iterations="${2:-5}"
    local token
    token="$(make_token)"
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" << EOF
---
session_id: "test-session-001"
task_id: "1.1"
iteration: ${iteration}
max_iterations: ${max_iterations}
plan_mode: false
project_dir: "${TEST_DIR}"
---

This is the prompt text for the verifier loop.
EOF
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"
    echo "$token"
}

# Helper: create a transcript file with optional content
create_transcript() {
    local transcript_path="$TEST_DIR/transcript.json"
    local content="${1:-no token here}"
    echo "$content" > "$transcript_path"
    echo "$transcript_path"
}

# --- Test 1: No state file, exit 0 (passthrough) ---
@test "no state file — exit 0 passthrough" {
    rm -f "$TEST_DIR/.claude/verifier-loop.local.md"
    run bash -c 'echo '"'"'{"transcript_path":"/dev/null"}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_success
}

# --- Test 2: Team mode active, exit 0 ---
@test "team mode active — exit 0 passthrough" {
    create_state
    touch "$TEST_DIR/.claude/vgl-team-active"
    run bash -c 'echo '"'"'{"transcript_path":"/dev/null"}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_success
}

# --- Test 3: Corrupted iteration — cleanup + exit 0 ---
@test "corrupted iteration — cleanup and exit 0" {
    local token
    token="$(make_token)"
    # Write a state file with non-numeric iteration
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" << EOF
---
session_id: "test-session-001"
task_id: "1.1"
iteration: GARBAGE
max_iterations: 5
plan_mode: false
project_dir: "${TEST_DIR}"
---

Prompt text here.
EOF
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"

    run bash -c 'echo '"'"'{"transcript_path":"/dev/null"}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_success
    # State file should be cleaned up
    assert [ ! -f "$TEST_DIR/.claude/verifier-loop.local.md" ]
}

# --- Test 4: Max iterations reached — cleanup + exit 0 ---
@test "max iterations reached — cleanup and exit 0" {
    # iteration=5, max_iterations=5 means iteration >= max
    create_state 5 5

    run bash -c 'echo '"'"'{"transcript_path":"/dev/null"}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_success
    # State should be cleaned up
    assert [ ! -f "$TEST_DIR/.claude/verifier-loop.local.md" ]
}

# --- Test 5: Token found in transcript — verification complete ---
@test "token found in transcript — verification complete" {
    local token
    token="$(create_state 1 5)"

    # Create a transcript containing the valid token
    local transcript_path
    transcript_path="$(create_transcript "some output... ${token} ...more output")"

    # Build the JSON input for the hook
    local input_json
    input_json="{\"transcript_path\": \"${transcript_path}\"}"

    run bash -c "echo '${input_json}' | bash '$HOOK' 2>&1"
    assert_success
    # State file cleaned up on successful token match (non-plan mode)
    assert [ ! -f "$TEST_DIR/.claude/verifier-loop.local.md" ]
}

# --- Test 6: Token not found — increments iteration, continues loop ---
@test "token not found — increments iteration and continues" {
    local token
    token="$(create_state 1 5)"

    # Create transcript without the token
    local transcript_path
    transcript_path="$(create_transcript "no completion token here")"

    # Build the JSON input
    local input_json
    input_json="{\"transcript_path\": \"${transcript_path}\"}"

    run bash -c "echo '${input_json}' | bash '$HOOK' 2>&1"
    # Should output JSON with "block" decision
    assert_success
    assert_output --partial '"decision"'
    assert_output --partial 'block'

    # The state file should still exist with updated iteration
    assert [ -f "$TEST_DIR/.claude/verifier-loop.local.md" ]

    # Check that iteration was incremented from 1 to 2
    run bash -c "grep '^iteration:' '$TEST_DIR/.claude/verifier-loop.local.md'"
    assert_output --partial "2"
}
