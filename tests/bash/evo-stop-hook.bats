#!/usr/bin/env bats
# evo-stop-hook.bats -- tests for evolution engine integration in hooks/stop-hook.sh
# Verifies: evo_eval.py called on failure, evo_db.py --add stores metrics,
# EVOLUTION CONTEXT injected, pollination on first iteration, graceful degradation.

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    HOOK="$HOOKS_DIR/stop-hook.sh"
    mkdir -p "$TEST_DIR/.claude/plan/tasks"
    mkdir -p "$TEST_DIR/.planning"

    # Create mock evo scripts directory
    MOCK_SCRIPTS_DIR="$TEST_DIR/mock_scripts"
    mkdir -p "$MOCK_SCRIPTS_DIR"

    # Tracking file for mock script invocations
    TRACK_FILE="$TEST_DIR/evo_tracking.log"
    touch "$TRACK_FILE"

    # Create mock evo_eval.py -- logs its invocation and outputs metrics JSON
    cat > "$MOCK_SCRIPTS_DIR/evo_eval.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, json, os
track = os.environ.get("EVO_TRACK_FILE", "/tmp/evo_tracking.log")
with open(track, "a") as f:
    f.write("evo_eval called: " + " ".join(sys.argv[1:]) + "\n")
print(json.dumps({
    "test_pass_rate": 0.5,
    "duration_s": 2.1,
    "complexity": 10,
    "todo_count": 0,
    "error_count": 2,
    "stage": 3,
    "artifacts": {"test_output": "2 passed, 2 failed", "error_trace": "AssertionError"}
}))
PYEOF
    chmod +x "$MOCK_SCRIPTS_DIR/evo_eval.py"

    # Create mock evo_db.py -- logs its invocation and outputs status JSON
    cat > "$MOCK_SCRIPTS_DIR/evo_db.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, json, os
track = os.environ.get("EVO_TRACK_FILE", "/tmp/evo_tracking.log")
with open(track, "a") as f:
    f.write("evo_db called: " + " ".join(sys.argv[1:]) + "\n")
# Handle --add: create population files to simulate persistence
for i, arg in enumerate(sys.argv):
    if arg == "--db-path" and i + 1 < len(sys.argv):
        db_path = sys.argv[i + 1]
        os.makedirs(db_path, exist_ok=True)
        # Write a minimal approaches.jsonl to simulate data
        approaches_file = os.path.join(db_path, "approaches.jsonl")
        with open(approaches_file, "a") as af:
            af.write(json.dumps({
                "id": "mock-approach-1",
                "prompt_addendum": "try harder",
                "parent_id": None,
                "generation": 0,
                "metrics": {"test_pass_rate": 0.5},
                "island": 0,
                "feature_coords": [0, 0],
                "task_id": "2.1",
                "task_type": "backend",
                "file_patterns": [],
                "artifacts": {},
                "timestamp": 1000000,
                "iteration": 1
            }) + "\n")
        break
print(json.dumps({"status": "added", "id": "mock-approach-1"}))
PYEOF
    chmod +x "$MOCK_SCRIPTS_DIR/evo_db.py"

    # Create mock evo_prompt.py -- logs invocation and outputs evolution context
    cat > "$MOCK_SCRIPTS_DIR/evo_prompt.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, json, os
track = os.environ.get("EVO_TRACK_FILE", "/tmp/evo_tracking.log")
with open(track, "a") as f:
    f.write("evo_prompt called: " + " ".join(sys.argv[1:]) + "\n")
print("## Evolution Context\n- Task: test\n- Population size: 1\n## Parent Approach\n> try harder\n## Your Directive\nImprove test pass rate.")
PYEOF
    chmod +x "$MOCK_SCRIPTS_DIR/evo_prompt.py"

    # Create mock evo_pollinator.py -- logs invocation
    cat > "$MOCK_SCRIPTS_DIR/evo_pollinator.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, json, os
track = os.environ.get("EVO_TRACK_FILE", "/tmp/evo_tracking.log")
with open(track, "a") as f:
    f.write("evo_pollinator called: " + " ".join(sys.argv[1:]) + "\n")
print(json.dumps({"migrated": 0, "source_tasks": [], "target_island": 2}))
PYEOF
    chmod +x "$MOCK_SCRIPTS_DIR/evo_pollinator.py"

    cd "$TEST_DIR"
}

teardown() {
    cd /
    if [[ -n "${TEST_DIR:-}" ]] && [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# Helper: generate a valid token
make_token() {
    echo "VGL_COMPLETE_0000000000000000ab54a98ceb1f0ad2"
}

# Helper: create state file with task_id and test_command in frontmatter
# Simulates a mismatch (token not in transcript) to trigger the retry path
create_state_with_task() {
    local iteration="${1:-1}"
    local max_iterations="${2:-5}"
    local task_id="${3:-2.1}"
    local test_command="${4:-echo pass}"
    local token
    token="$(make_token)"
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" << EOF
---
session_id: "test-session-evo"
task_id: "${task_id}"
iteration: ${iteration}
max_iterations: ${max_iterations}
plan_mode: false
project_dir: "${TEST_DIR}"
test_command: "${test_command}"
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
---

This is the prompt text for the evolution test.
EOF
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"
    echo "$token"
}

# Helper: create a transcript without token (triggers mismatch/retry path)
create_transcript_no_token() {
    local transcript_path="$TEST_DIR/transcript.json"
    echo "some output without any completion token" > "$transcript_path"
    echo "$transcript_path"
}

# Helper: run the hook with the PLUGIN_ROOT override to use mock scripts
# We override the hook's PLUGIN_ROOT detection by symlinking hooks/ into our mock structure
run_hook_with_mocks() {
    local input_json="$1"
    # Create a symlink structure so PLUGIN_ROOT resolves to our mock dir
    # The hook does: PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
    # So if the hook is at $MOCK_ROOT/hooks/stop-hook.sh, PLUGIN_ROOT=$MOCK_ROOT
    local MOCK_ROOT="$TEST_DIR/mock_plugin"
    mkdir -p "$MOCK_ROOT/hooks"
    mkdir -p "$MOCK_ROOT/scripts"

    # Copy the real hook
    cp "$HOOK" "$MOCK_ROOT/hooks/stop-hook.sh"
    chmod +x "$MOCK_ROOT/hooks/stop-hook.sh"

    # Symlink mock scripts into the mock plugin scripts dir
    ln -sf "$MOCK_SCRIPTS_DIR/evo_eval.py" "$MOCK_ROOT/scripts/evo_eval.py"
    ln -sf "$MOCK_SCRIPTS_DIR/evo_db.py" "$MOCK_ROOT/scripts/evo_db.py"
    ln -sf "$MOCK_SCRIPTS_DIR/evo_prompt.py" "$MOCK_ROOT/scripts/evo_prompt.py"
    ln -sf "$MOCK_SCRIPTS_DIR/evo_pollinator.py" "$MOCK_ROOT/scripts/evo_pollinator.py"

    # Set the tracking env var so mock scripts know where to log
    export EVO_TRACK_FILE="$TRACK_FILE"

    echo "$input_json" | bash "$MOCK_ROOT/hooks/stop-hook.sh" 2>&1
}

# --- Test 1: evo_eval.py called on verification failure ---
@test "evo_eval called on verification failure (token mismatch)" {
    create_state_with_task 1 5 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    run run_hook_with_mocks "$input_json"
    assert_success

    # Verify evo_eval.py was invoked
    run cat "$TRACK_FILE"
    assert_output --partial "evo_eval called"
    assert_output --partial "--evaluate"
}

# --- Test 2: evo_db.py --add called with metrics after evaluation ---
@test "evo_db --add called with metrics JSON after evaluation" {
    create_state_with_task 1 5 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    run run_hook_with_mocks "$input_json"
    assert_success

    # Verify evo_db.py was invoked with --add
    run cat "$TRACK_FILE"
    assert_output --partial "evo_db called"
    assert_output --partial "--add"
    assert_output --partial "--db-path"
}

# --- Test 3: next prompt output JSON contains EVOLUTION CONTEXT ---
@test "evolution context injected into retry prompt" {
    create_state_with_task 2 5 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    run run_hook_with_mocks "$input_json"
    assert_success

    # The output JSON reason field should contain EVOLUTION CONTEXT
    assert_output --partial "EVOLUTION CONTEXT"
    # Should also contain Evolution-guided in systemMessage
    assert_output --partial "Evolution-guided"
}

# --- Test 4: pollination called on first iteration ---
@test "first iteration triggers pollination" {
    create_state_with_task 1 5 "2.1" "echo pass"

    # Create plan.yaml for pollinator
    cat > "$TEST_DIR/.claude/plan/plan.yaml" << 'YAML'
metadata:
  project: "test-project"
phases:
  - id: 1
    name: "Phase 1"
    tasks:
      - id: "2.1"
        name: "Current Task"
        status: "in_progress"
YAML

    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    run run_hook_with_mocks "$input_json"
    assert_success

    # Verify pollinator was called on first iteration
    run cat "$TRACK_FILE"
    assert_output --partial "evo_pollinator called"
    assert_output --partial "--pollinate"
}

# --- Test 5: graceful degradation without evo scripts ---
@test "graceful degradation without evo scripts" {
    create_state_with_task 1 5 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    # Remove all evo scripts from mock dir
    rm -f "$MOCK_SCRIPTS_DIR/evo_eval.py"
    rm -f "$MOCK_SCRIPTS_DIR/evo_db.py"
    rm -f "$MOCK_SCRIPTS_DIR/evo_prompt.py"
    rm -f "$MOCK_SCRIPTS_DIR/evo_pollinator.py"

    run run_hook_with_mocks "$input_json"
    assert_success

    # Should still output valid JSON with "block" decision
    assert_output --partial '"decision"'
    assert_output --partial 'block'
}

# --- Test 6: population directory created on first hook invocation ---
@test "population directory created on first invocation" {
    create_state_with_task 1 5 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    run run_hook_with_mocks "$input_json"
    assert_success

    # The population directory should be created
    assert [ -d "$TEST_DIR/.planning/evolution/2.1" ]
}

# --- Test 7: empty population on first iteration produces valid JSON ---
@test "empty population on first iteration produces valid JSON" {
    create_state_with_task 1 5 "3.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    # No pre-existing population data
    run run_hook_with_mocks "$input_json"
    assert_success

    # Should output valid JSON
    assert_output --partial '"decision"'
    assert_output --partial 'block'
    # Should contain the prompt text from the state file
    assert_output --partial 'prompt text for the evolution test'
}

# --- Test 8: population persists across two hook runs ---
@test "population persists across two failed iterations" {
    create_state_with_task 1 5 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    # First run
    run run_hook_with_mocks "$input_json"
    assert_success

    # Second run: iteration is now 2 (incremented by first run)
    # Re-create transcript (state file was updated in place)
    transcript_path="$(create_transcript_no_token)"
    input_json="{\"transcript_path\": \"${transcript_path}\"}"

    run run_hook_with_mocks "$input_json"
    assert_success

    # Population directory should exist with data
    assert [ -d "$TEST_DIR/.planning/evolution/2.1" ]
    # The approaches.jsonl should have at least 2 entries (one per run)
    local line_count
    line_count=$(wc -l < "$TEST_DIR/.planning/evolution/2.1/approaches.jsonl" 2>/dev/null || echo "0")
    [ "$line_count" -ge 2 ]
}
