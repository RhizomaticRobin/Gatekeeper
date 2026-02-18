#!/usr/bin/env bats
# guard-skills.bats — tests for hooks/guard-skills.sh
# Verifies skill gating behavior during active VGL loops.

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

# --- Test 1: No VGL active, any skill exits 0 ---
@test "no VGL active — any skill allowed (exit 0)" {
    # No .claude/verifier-loop.local.md file exists
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:quest"}}'"'"' | bash "'"$HOOK"'"'
    assert_success
}

# --- Test 2: VGL active, cross-team allowed ---
@test "VGL active — cross-team allowed (exit 0)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:cross-team"}}'"'"' | bash "'"$HOOK"'"'
    assert_success
}

# --- Test 3: VGL active, progress allowed ---
@test "VGL active — progress allowed (exit 0)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:progress"}}'"'"' | bash "'"$HOOK"'"'
    assert_success
}

# --- Test 4: VGL active, quest blocked (exit 2) ---
@test "VGL active — quest blocked (exit 2 with BLOCKED)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:quest"}}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_failure 2
    assert_output --partial "BLOCKED"
}

# --- Test 5: VGL active, bridge blocked ---
@test "VGL active — bridge blocked (exit 2)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:bridge"}}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_failure 2
}

# --- Test 6: VGL active, run-away blocked ---
@test "VGL active — run-away blocked (exit 2)" {
    mkdir -p .claude
    touch .claude/verifier-loop.local.md
    run bash -c 'echo '"'"'{"tool_input":{"skill":"gatekeeper:run-away"}}'"'"' | bash "'"$HOOK"'" 2>&1'
    assert_failure 2
}

# --- Test 7: VGL active, new-project blocked ---
@test "VGL active — new-project blocked (exit 2)" {
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
