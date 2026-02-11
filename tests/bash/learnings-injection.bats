#!/usr/bin/env bats
# learnings-injection.bats — tests for learnings injection into task prompts
# Verifies that stop-hook.sh queries learnings.py --relevant before building
# NEXT_TASK_PROMPT and formats relevant learnings as bullet points.

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    HOOK="$HOOKS_DIR/stop-hook.sh"
    mkdir -p "$TEST_DIR/.claude/plan/tasks"
    mkdir -p "$TEST_DIR/.planning"

    # Create plan with task 1.1 completed and 1.2 pending
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
        status: "completed"
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
      - id: "1.2"
        name: "Task B"
        status: "pending"
        depends_on:
          - "1.1"
        deliverables:
          backend: "test"
          frontend: "test"
        tests:
          quantitative:
            command: "echo pass"
          qualitative:
            criteria:
              - "works"
        prompt_file: "tasks/task-1.2.md"
YAML

    # Create task prompt file for 1.2
    cat > "$TEST_DIR/.claude/plan/tasks/task-1.2.md" <<'MD'
# Task 1.2: Task B

Implement Task B features.
MD

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

# Helper: create state file for plan mode with task 1.1 complete, triggering transition to 1.2
create_plan_state() {
    local token
    token="$(make_token)"
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<EOF
---
session_id: "test-session-learn"
task_id: "1.1"
iteration: 1
max_iterations: 5
plan_mode: true
project_dir: "${TEST_DIR}"
started_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
---

This is the prompt for task 1.1.
EOF
    echo "$token" > "$TEST_DIR/.claude/verifier-token.secret"
    echo "$token"
}

# Helper: create a transcript file containing the token
create_transcript_with_token() {
    local token="$1"
    local transcript_path="$TEST_DIR/transcript.json"
    echo "some output... ${token} ...more output" > "$transcript_path"
    echo "$transcript_path"
}

# Helper: create a learnings.jsonl with relevant entries
create_learnings_file() {
    mkdir -p "$TEST_DIR/.planning"
    cat > "$TEST_DIR/.planning/learnings.jsonl" <<'JSONL'
{"task_id": "1.1", "category": "fix_pattern", "description": "Always check for null before accessing nested properties", "file_patterns": ["hooks/stop-hook.sh"], "task_type": "backend", "timestamp": "2026-02-10T12:00:00Z"}
{"task_id": "1.1", "category": "test_pattern", "description": "Use waitFor for async assertions in component tests", "file_patterns": ["tests/bash/smoke.bats"], "task_type": "test", "timestamp": "2026-02-10T13:00:00Z"}
JSONL
}

# --- Test 1: Prompt includes learnings when available ---
@test "prompt includes LEARNINGS section when relevant learnings exist" {
    local token
    token="$(create_plan_state)"

    # Create learnings file with entries that will match based on task_type
    create_learnings_file

    local transcript_path
    transcript_path="$(create_transcript_with_token "$token")"

    local input_json
    input_json="{\"transcript_path\": \"${transcript_path}\"}"

    # Run the stop hook (which triggers transition to next task)
    run bash -c "echo '${input_json}' | bash '$HOOK' 2>/dev/null"
    assert_success

    # The output should be JSON with "decision":"block" containing the next task prompt
    # The prompt (in "reason" field) should contain LEARNINGS section
    assert_output --partial 'LEARNINGS FROM PREVIOUS RUNS'
}

# --- Test 2: Prompt is clean when no learnings exist ---
@test "prompt is clean when no learnings exist" {
    local token
    token="$(create_plan_state)"

    # Ensure no learnings file exists
    rm -f "$TEST_DIR/.planning/learnings.jsonl"

    local transcript_path
    transcript_path="$(create_transcript_with_token "$token")"

    local input_json
    input_json="{\"transcript_path\": \"${transcript_path}\"}"

    run bash -c "echo '${input_json}' | bash '$HOOK' 2>/dev/null"
    assert_success

    # Output should NOT contain LEARNINGS section
    refute_output --partial 'LEARNINGS FROM PREVIOUS RUNS'

    # But should still contain a valid task prompt transition
    assert_output --partial '"decision"'
}

# --- Test 3: Graceful when learnings.py missing ---
@test "graceful degradation when learnings.py is missing" {
    local token
    token="$(create_plan_state)"

    # Create learnings file (but learnings.py will be missing)
    create_learnings_file

    local transcript_path
    transcript_path="$(create_transcript_with_token "$token")"

    local input_json
    input_json="{\"transcript_path\": \"${transcript_path}\"}"

    # Temporarily rename learnings.py to simulate it being missing
    local learnings_py="$SCRIPTS_DIR/learnings.py"
    if [[ -f "$learnings_py" ]]; then
        mv "$learnings_py" "${learnings_py}.bak"
    fi

    run bash -c "echo '${input_json}' | bash '$HOOK' 2>/dev/null"

    # Restore learnings.py
    if [[ -f "${learnings_py}.bak" ]]; then
        mv "${learnings_py}.bak" "$learnings_py"
    fi

    assert_success

    # Prompt should still be generated without errors, just without LEARNINGS section
    refute_output --partial 'LEARNINGS FROM PREVIOUS RUNS'
    assert_output --partial '"decision"'
}
