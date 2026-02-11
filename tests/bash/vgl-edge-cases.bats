#!/usr/bin/env bats
# vgl-edge-cases.bats — tests for VGL edge case hardening
# Covers: empty state, missing session_id, malformed JSON, expired sessions,
#         token permissions, started_at frontmatter.

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    HOOK="$HOOKS_DIR/stop-hook.sh"
    SETUP="$SCRIPTS_DIR/setup-verifier-loop.sh"
    mkdir -p "$TEST_DIR/.claude"
    cd "$TEST_DIR"
}

teardown() {
    if [[ -n "${TEST_DIR:-}" ]] && [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# Helper: generate a valid token
make_token() {
    echo "VGL_COMPLETE_0000000000000000ab54a98ceb1f0ad2"
}

# --- Test 1: stop-hook with empty state file — cleanup + exit 0 ---
@test "stop-hook with empty state file — cleanup and exit 0" {
    # Create an empty state file
    touch "$TEST_DIR/.claude/verifier-loop.local.md"
    local token
    token="$(make_token)"
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"

    run bash -c 'echo '"'"'{"transcript_path":"/dev/null"}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_success

    # State file should be cleaned up
    assert [ ! -f "$TEST_DIR/.claude/verifier-loop.local.md" ]
}

# --- Test 2: stop-hook with missing session_id — cleanup + exit 0 ---
@test "stop-hook with missing session_id — cleanup and exit 0" {
    # Create a state file without session_id
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" << EOF
---
iteration: 1
max_iterations: 5
project_dir: "${TEST_DIR}"
---

Prompt text without session_id.
EOF
    local token
    token="$(make_token)"
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"

    run bash -c 'echo '"'"'{"transcript_path":"/dev/null"}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_success

    # State file should be cleaned up
    assert [ ! -f "$TEST_DIR/.claude/verifier-loop.local.md" ]
}

# --- Test 3: stop-hook with malformed JSON input — exit 0 (passthrough) ---
@test "stop-hook with malformed JSON input — exit 0 passthrough" {
    # Create a valid state file so we get past the "no state file" check
    local token
    token="$(make_token)"
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" << EOF
---
session_id: "test-session-json"
iteration: 1
max_iterations: 5
project_dir: "${TEST_DIR}"
started_at: "2026-02-11T00:00:00Z"
---

Prompt text here.
EOF
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"

    # Send completely malformed JSON (not valid JSON at all)
    run bash -c 'echo "THIS IS NOT JSON AT ALL" | bash "'"$HOOK"'" 2>&1'
    assert_success
}

# --- Test 4: stop-hook with expired session (>24h) — warn + cleanup ---
@test "stop-hook with expired session — warn and cleanup" {
    # Create a state file with started_at 25 hours ago
    local stale_time
    stale_time=$(date -u -d "25 hours ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-25H +%Y-%m-%dT%H:%M:%SZ)
    local token
    token="$(make_token)"

    cat > "$TEST_DIR/.claude/verifier-loop.local.md" << EOF
---
session_id: "stale-session-001"
iteration: 1
max_iterations: 5
project_dir: "${TEST_DIR}"
started_at: "${stale_time}"
---

Prompt text for stale session.
EOF
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"
    touch "$TEST_DIR/.claude/verifier-prompt.local.md"

    # Create transcript without token
    echo "no token here" > "$TEST_DIR/transcript.json"
    local input_json
    input_json="{\"transcript_path\": \"$TEST_DIR/transcript.json\"}"

    run bash -c "echo '${input_json}' | bash '$HOOK' 2>&1"
    assert_success

    # Should mention stale/expired
    assert_output --partial "stale"

    # State files should be cleaned up
    assert [ ! -f "$TEST_DIR/.claude/verifier-loop.local.md" ]
    assert [ ! -f "$TEST_DIR/.claude/verifier-prompt.local.md" ]
    assert [ ! -f "$TEST_DIR/.claude/verifier-token.secret" ]
}

# --- Test 5: token file has 600 permissions after setup-verifier-loop ---
@test "token file has 600 permissions after setup-verifier-loop" {
    run bash -c "cd '$TEST_DIR' && bash '$SETUP' --verification-criteria 'test' --test-command 'echo pass' test_prompt 2>&1"
    assert_success

    # Check that token file exists
    assert [ -f "$TEST_DIR/.claude/verifier-token.secret" ]

    # Check permissions are 600
    local perms
    perms=$(stat -c '%a' "$TEST_DIR/.claude/verifier-token.secret" 2>/dev/null || stat -f '%A' "$TEST_DIR/.claude/verifier-token.secret")
    assert_equal "$perms" "600"
}

# --- Test 6: setup-verifier-loop adds started_at to frontmatter ---
@test "setup-verifier-loop adds started_at to frontmatter" {
    run bash -c "cd '$TEST_DIR' && bash '$SETUP' --verification-criteria 'test' --test-command 'echo pass' test_prompt 2>&1"
    assert_success

    # Check state file exists
    assert [ -f "$TEST_DIR/.claude/verifier-loop.local.md" ]

    # Check started_at field in frontmatter
    run bash -c "grep 'started_at:' '$TEST_DIR/.claude/verifier-loop.local.md'"
    assert_success
    assert_output --partial "started_at:"

    # Validate it looks like an ISO 8601 timestamp
    run bash -c "grep -oP 'started_at: \"\\K[^\"]+' '$TEST_DIR/.claude/verifier-loop.local.md'"
    assert_success
    # Should match YYYY-MM-DDTHH:MM:SSZ pattern
    assert_output --regexp '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
}
