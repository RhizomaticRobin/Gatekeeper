#!/usr/bin/env bats
# guard-skills.bats — tests for hooks/guard-skills.sh
# Verifies skill gating behavior during active Gatekeeper loops.

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    HOOK="$HOOKS_DIR/guard-skills.sh"
    cd "$TEST_DIR"
}

teardown() {
    if [[ -n "${TEST_DIR:-}" ]] && [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# --- Test 1: No Gatekeeper active, any skill exits 0 ---
@test "no Gatekeeper active — any skill allowed (exit 0)" {
    # No .claude/verifier-loop.local.md file exists
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:quest"}}'"'"' | bash "'"$HOOK"'"'
    assert_success
}

# --- Test 2: Gatekeeper active, cross-team allowed ---
@test "Gatekeeper active — cross-team allowed (exit 0)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:cross-team"}}'"'"' | bash "'"$HOOK"'"'
    assert_success
}

# --- Test 3: Gatekeeper active, quest blocked (exit 2) ---
@test "Gatekeeper active — quest blocked (exit 2 with BLOCKED)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:quest"}}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_failure 2
    assert_output --partial "BLOCKED"
}

# --- Test 4: Gatekeeper active, run-away blocked ---
@test "Gatekeeper active — run-away blocked (exit 2)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:run-away"}}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_failure 2
}

# --- Test 7: Gatekeeper active, new-project blocked ---
@test "Gatekeeper active — new-project blocked (exit 2)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:new-project"}}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_failure 2
}

# --- Test 8: Non-gatekeeper skill always allowed ---
@test "non-gatekeeper skill — allowed (exit 0)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"some-other-plugin:do-stuff"}}'"'"' | bash "'"$HOOK"'"'
    assert_success
}

# --- Test 9: No skill in input exits 0 ---
@test "no skill in input — allowed (exit 0)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"foo":"bar"}}'"'"' | bash "'"$HOOK"'"'
    assert_success
}

# --- Test 10: Bare skill name (cross-team without prefix) allowed ---
@test "bare skill name cross-team — allowed (exit 0)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"cross-team"}}'"'"' | bash "'"$HOOK"'"'
    assert_success
}
