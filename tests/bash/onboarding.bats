#!/usr/bin/env bats
# onboarding.bats — tests for first-run onboarding detection and welcome message
#
# Task 5.3: First-Run Onboarding
# Verifies:
#   - First-run detected by absence of .planning/ directory
#   - Welcome message is 3 lines max
#   - Welcome only shown once per project
#   - Marker file (.planning/.initialized) created after welcome
#   - Welcome includes help reference

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    cd "$TEST_DIR"
}

teardown() {
    cd /
    if [[ -n "${TEST_DIR:-}" ]] && [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# =============================================================================
# Test 1: welcome shown on first run — no .planning/ dir means welcome output
# =============================================================================
@test "welcome shown on first run — no .planning/ directory triggers welcome message" {
    # No .planning/ directory exists
    [ ! -d "$TEST_DIR/.planning" ]
    run bash "$SCRIPTS_DIR/onboarding.sh"
    assert_success
    assert_output --partial "Welcome to EvoGatekeeper"
    assert_output --partial "new-project"
}

# =============================================================================
# Test 2: welcome not shown after init — .planning/.initialized exists
# =============================================================================
@test "welcome not shown after init — .planning/.initialized exists skips welcome" {
    mkdir -p "$TEST_DIR/.planning"
    touch "$TEST_DIR/.planning/.initialized"
    run bash "$SCRIPTS_DIR/onboarding.sh"
    assert_success
    refute_output --partial "Welcome to EvoGatekeeper"
}

# =============================================================================
# Test 3: welcome not shown with planning dir — .planning/ exists
# =============================================================================
@test "welcome not shown with planning dir — .planning/ exists skips welcome" {
    mkdir -p "$TEST_DIR/.planning"
    run bash "$SCRIPTS_DIR/onboarding.sh"
    assert_success
    refute_output --partial "Welcome to EvoGatekeeper"
}

# =============================================================================
# Test 4: welcome includes help reference
# =============================================================================
@test "welcome includes help reference — output contains /gsd-vgl:help" {
    # No .planning/ directory — first run
    [ ! -d "$TEST_DIR/.planning" ]
    run bash "$SCRIPTS_DIR/onboarding.sh"
    assert_success
    assert_output --partial "/gsd-vgl:help"
}

# =============================================================================
# Test 5: marker file created — .planning/.initialized created after welcome
# =============================================================================
@test "marker file created — .planning/.initialized created after welcome" {
    # No .planning/ directory — first run
    [ ! -d "$TEST_DIR/.planning" ]
    run bash "$SCRIPTS_DIR/onboarding.sh"
    assert_success
    # After running onboarding, the marker file should exist
    [ -f "$TEST_DIR/.planning/.initialized" ]
}

# =============================================================================
# Test 6: welcome message is 3 lines max
# =============================================================================
@test "welcome message is at most 3 lines" {
    # No .planning/ directory — first run
    [ ! -d "$TEST_DIR/.planning" ]
    run bash "$SCRIPTS_DIR/onboarding.sh"
    assert_success
    # Count non-empty lines in output
    line_count=$(echo "$output" | grep -c '.' || true)
    [ "$line_count" -le 3 ]
}
