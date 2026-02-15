#!/usr/bin/env bats
# stop-hook.bats — tests for hooks/stop-hook.sh
# Verifies VGL loop controller behavior: passthrough, iteration, token matching,
# and resilience integration (record-failure, check-all, record-success/reset).

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    HOOK="$HOOKS_DIR/stop-hook.sh"
    mkdir -p "$TEST_DIR/.claude"
    mkdir -p "$TEST_DIR/.claude/plan/tasks"
    mkdir -p "$TEST_DIR/.planning"

    # Tracking file for mock script invocations (used by resilience tests)
    RESILIENCE_TRACK_FILE="$TEST_DIR/resilience_tracking.log"
    touch "$RESILIENCE_TRACK_FILE"

    cd "$TEST_DIR"
}

teardown() {
    cd /
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

# ============================================================
# Resilience Integration Tests
# ============================================================

# Helper: create state with task_id and test_command for resilience tests
create_state_for_resilience() {
    local iteration="${1:-1}"
    local max_iterations="${2:-0}"
    local task_id="${3:-2.1}"
    local test_command="${4:-echo pass}"
    local token
    token="$(make_token)"
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" << EOF
---
session_id: "test-session-res"
task_id: "${task_id}"
iteration: ${iteration}
max_iterations: ${max_iterations}
plan_mode: false
project_dir: "${TEST_DIR}"
test_command: "${test_command}"
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
---

This is the prompt text for resilience testing.
EOF
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"
    echo "$token"
}

# Helper: create transcript without token (triggers failure/retry path)
create_transcript_no_token() {
    local transcript_path="$TEST_DIR/transcript.json"
    echo "some output without any completion token" > "$transcript_path"
    echo "$transcript_path"
}

# Helper: set up mock plugin root with resilience.py mock and optionally evo scripts
# The hook resolves PLUGIN_ROOT from its own path: dirname(dirname(realpath($0)))
# So we create $MOCK_ROOT/hooks/stop-hook.sh -> PLUGIN_ROOT=$MOCK_ROOT
setup_mock_plugin_root() {
    local MOCK_ROOT="$TEST_DIR/mock_plugin"
    mkdir -p "$MOCK_ROOT/hooks"
    mkdir -p "$MOCK_ROOT/scripts"

    # Copy the real hook
    cp "$HOOK" "$MOCK_ROOT/hooks/stop-hook.sh"
    chmod +x "$MOCK_ROOT/hooks/stop-hook.sh"

    echo "$MOCK_ROOT"
}

# Helper: create mock resilience.py that logs calls and exits 0
create_mock_resilience_pass() {
    local mock_root="$1"
    cat > "$mock_root/scripts/resilience.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, os
track = os.environ.get("RESILIENCE_TRACK_FILE", "/tmp/resilience_tracking.log")
with open(track, "a") as f:
    f.write("resilience called: " + " ".join(sys.argv[1:]) + "\n")
sys.exit(0)
PYEOF
    chmod +x "$mock_root/scripts/resilience.py"
}

# Helper: create mock resilience.py that exits 1 for --check-all with stuck message
create_mock_resilience_stuck() {
    local mock_root="$1"
    cat > "$mock_root/scripts/resilience.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, os
track = os.environ.get("RESILIENCE_TRACK_FILE", "/tmp/resilience_tracking.log")
with open(track, "a") as f:
    f.write("resilience called: " + " ".join(sys.argv[1:]) + "\n")
# If --check-all is in args, exit 1 with stuck message
if "--check-all" in sys.argv:
    print("Stuck on task 2.1 (3 consecutive failures, threshold: 3)")
    sys.exit(1)
sys.exit(0)
PYEOF
    chmod +x "$mock_root/scripts/resilience.py"
}

# Helper: create mock evo scripts (pass-through, for ordering tests)
create_mock_evo_scripts() {
    local mock_root="$1"
    cat > "$mock_root/scripts/evo_eval.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, json, os, time
track = os.environ.get("RESILIENCE_TRACK_FILE", "/tmp/resilience_tracking.log")
with open(track, "a") as f:
    f.write("evo_eval called: " + " ".join(sys.argv[1:]) + " timestamp:" + str(time.time()) + "\n")
print(json.dumps({"test_pass_rate": 0.5, "duration_s": 1.0, "stage": 1, "artifacts": {}}))
PYEOF
    chmod +x "$mock_root/scripts/evo_eval.py"

    cat > "$mock_root/scripts/evo_db.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, json, os
track = os.environ.get("RESILIENCE_TRACK_FILE", "/tmp/resilience_tracking.log")
with open(track, "a") as f:
    f.write("evo_db called: " + " ".join(sys.argv[1:]) + "\n")
for i, arg in enumerate(sys.argv):
    if arg == "--db-path" and i + 1 < len(sys.argv):
        db_path = sys.argv[i + 1]
        os.makedirs(db_path, exist_ok=True)
        break
print(json.dumps({"status": "added"}))
PYEOF
    chmod +x "$mock_root/scripts/evo_db.py"

    cat > "$mock_root/scripts/evo_prompt.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, os
track = os.environ.get("RESILIENCE_TRACK_FILE", "/tmp/resilience_tracking.log")
with open(track, "a") as f:
    f.write("evo_prompt called: " + " ".join(sys.argv[1:]) + "\n")
print("## Evolution Context\n- mock context")
PYEOF
    chmod +x "$mock_root/scripts/evo_prompt.py"

    cat > "$mock_root/scripts/evo_pollinator.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, json, os
track = os.environ.get("RESILIENCE_TRACK_FILE", "/tmp/resilience_tracking.log")
with open(track, "a") as f:
    f.write("evo_pollinator called: " + " ".join(sys.argv[1:]) + "\n")
print(json.dumps({"migrated": 0}))
PYEOF
    chmod +x "$mock_root/scripts/evo_pollinator.py"
}

# Helper: run the hook using a mock plugin root
run_hook_with_resilience_mocks() {
    local mock_root="$1"
    local input_json="$2"
    export RESILIENCE_TRACK_FILE="$RESILIENCE_TRACK_FILE"
    export EVO_TRACK_FILE="$RESILIENCE_TRACK_FILE"
    echo "$input_json" | bash "$mock_root/hooks/stop-hook.sh" 2>&1
}

# --- Resilience Test 1: --record-failure called on failed iteration ---
@test "resilience: record-failure called on failed iteration" {
    create_state_for_resilience 1 0 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    local mock_root
    mock_root="$(setup_mock_plugin_root)"
    create_mock_resilience_pass "$mock_root"
    create_mock_evo_scripts "$mock_root"

    # Create plan.yaml for resilience config extraction
    cat > "$TEST_DIR/.claude/plan/plan.yaml" << 'YAML'
metadata:
  project: "test-project"
  stuck_threshold: 3
  circuit_breaker_threshold: 5
phases:
  - id: 1
    name: "Phase 1"
    tasks:
      - id: "2.1"
        name: "Test Task"
        status: "in_progress"
YAML

    run run_hook_with_resilience_mocks "$mock_root" "$input_json"
    assert_success

    # Verify resilience.py was called with --record-failure and the task ID
    run cat "$RESILIENCE_TRACK_FILE"
    assert_output --partial "resilience called"
    assert_output --partial "--record-failure"
    assert_output --partial "2.1"
}

# --- Resilience Test 2: --check-all exits 1 (stuck) → cleanup + exit ---
@test "resilience: check-all stuck triggers cleanup and exit" {
    create_state_for_resilience 1 0 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    local mock_root
    mock_root="$(setup_mock_plugin_root)"
    create_mock_resilience_stuck "$mock_root"
    create_mock_evo_scripts "$mock_root"

    # Create plan.yaml
    cat > "$TEST_DIR/.claude/plan/plan.yaml" << 'YAML'
metadata:
  project: "test-project"
  stuck_threshold: 3
  circuit_breaker_threshold: 5
phases:
  - id: 1
    name: "Phase 1"
    tasks:
      - id: "2.1"
        name: "Test Task"
        status: "in_progress"
YAML

    run run_hook_with_resilience_mocks "$mock_root" "$input_json"
    assert_success

    # Verify the stuck message is in output
    assert_output --partial "Stuck on task"
    assert_output --partial "Stopping due to resilience check failure"

    # State files should be cleaned up
    assert [ ! -f "$TEST_DIR/.claude/verifier-loop.local.md" ]
    assert [ ! -f "$TEST_DIR/.claude/verifier-token.secret" ]
}

# --- Resilience Test 3: --record-success and --reset called on token match ---
@test "resilience: record-success and reset called on token match" {
    local token
    token="$(create_state_for_resilience 1 0 "2.1" "echo pass")"

    # Create a transcript CONTAINING the token (success path)
    local transcript_path
    transcript_path="$(create_transcript "some output... ${token} ...more output")"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    local mock_root
    mock_root="$(setup_mock_plugin_root)"
    create_mock_resilience_pass "$mock_root"

    run run_hook_with_resilience_mocks "$mock_root" "$input_json"
    assert_success

    # Verify resilience.py was called with --record-success and --reset
    run cat "$RESILIENCE_TRACK_FILE"
    assert_output --partial "--record-success"
    assert_output --partial "--reset"
}

# --- Resilience Test 4: missing resilience.py — graceful degradation ---
@test "resilience: missing resilience.py — graceful degradation" {
    create_state_for_resilience 1 0 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    local mock_root
    mock_root="$(setup_mock_plugin_root)"
    create_mock_evo_scripts "$mock_root"
    # Do NOT create resilience.py — it should be missing

    run run_hook_with_resilience_mocks "$mock_root" "$input_json"
    assert_success

    # Hook should still produce the block JSON to continue the loop
    assert_output --partial '"decision"'
    assert_output --partial 'block'
}

# --- Resilience Test 5: evolution runs BEFORE resilience on failure path ---
@test "resilience: evolution runs before resilience check" {
    create_state_for_resilience 1 0 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    local mock_root
    mock_root="$(setup_mock_plugin_root)"
    create_mock_evo_scripts "$mock_root"

    # Create a resilience.py that also logs timestamp
    cat > "$mock_root/scripts/resilience.py" << 'PYEOF'
#!/usr/bin/env python3
import sys, os, time
track = os.environ.get("RESILIENCE_TRACK_FILE", "/tmp/resilience_tracking.log")
with open(track, "a") as f:
    f.write("resilience called: " + " ".join(sys.argv[1:]) + " timestamp:" + str(time.time()) + "\n")
sys.exit(0)
PYEOF
    chmod +x "$mock_root/scripts/resilience.py"

    # Create plan.yaml
    cat > "$TEST_DIR/.claude/plan/plan.yaml" << 'YAML'
metadata:
  project: "test-project"
  stuck_threshold: 3
  circuit_breaker_threshold: 5
phases:
  - id: 1
    name: "Phase 1"
    tasks:
      - id: "2.1"
        name: "Test Task"
        status: "in_progress"
YAML

    run run_hook_with_resilience_mocks "$mock_root" "$input_json"
    assert_success

    # Extract timestamps: evo_eval should appear BEFORE resilience
    local evo_line resilience_line evo_lineno resilience_lineno
    evo_lineno=$(grep -n "evo_eval called" "$RESILIENCE_TRACK_FILE" | head -1 | cut -d: -f1)
    resilience_lineno=$(grep -n "resilience called.*--record-failure" "$RESILIENCE_TRACK_FILE" | head -1 | cut -d: -f1)

    # evo_eval must appear on an earlier line than resilience
    [ -n "$evo_lineno" ]
    [ -n "$resilience_lineno" ]
    [ "$evo_lineno" -lt "$resilience_lineno" ]
}

# --- Resilience Test 6: --check-all called with config from plan.yaml ---
@test "resilience: check-all called with config from plan.yaml metadata" {
    create_state_for_resilience 1 0 "2.1" "echo pass"
    local transcript_path
    transcript_path="$(create_transcript_no_token)"
    local input_json="{\"transcript_path\": \"${transcript_path}\"}"

    local mock_root
    mock_root="$(setup_mock_plugin_root)"
    create_mock_resilience_pass "$mock_root"
    create_mock_evo_scripts "$mock_root"

    # Create plan.yaml with specific resilience metadata
    cat > "$TEST_DIR/.claude/plan/plan.yaml" << 'YAML'
metadata:
  project: "test-project"
  stuck_threshold: 3
  circuit_breaker_threshold: 5
  max_vgl_iterations: 50
  timeout_hours: 8
phases:
  - id: 1
    name: "Phase 1"
    tasks:
      - id: "2.1"
        name: "Test Task"
        status: "in_progress"
YAML

    run run_hook_with_resilience_mocks "$mock_root" "$input_json"
    assert_success

    # Verify --check-all was called with the task ID and --config
    run cat "$RESILIENCE_TRACK_FILE"
    assert_output --partial "--check-all"
    assert_output --partial "2.1"
    assert_output --partial "--config"
}
