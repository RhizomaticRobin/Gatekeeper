#!/usr/bin/env bats
# Tests for history recording integration in transition-task.sh
# Verifies that transition-task.sh calls run_history.py --record after task completion
# and that duration is calculated from the first iteration timestamp.

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    mkdir -p "$TEST_DIR/.claude/plan/tasks"
    mkdir -p "$TEST_DIR/.planning/history"

    # Create a plan with task 1.1 pending and 1.2 pending
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
        status: "pending"
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

    # Create state file pointing to task 1.1, with started_at and iteration
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<EOF
---
session_id: "test-session-hist"
task_id: "1.1"
iteration: 3
max_iterations: 5
project_dir: "/tmp/test"
started_at: "$(date -u -d '120 seconds ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-120S +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo '2026-02-11T00:00:00Z')"
plan_mode: true
---

Test prompt content
EOF
    cd "$TEST_DIR"
}

teardown() {
    cd /
    rm -rf "$TEST_DIR"
}

@test "transition-task records history entry after completing task" {
    run "$SCRIPTS_DIR/transition-task.sh"
    # transition should still succeed (exit 0 means next task found)
    assert_success

    # History file should exist with at least one entry
    assert_file_exists "$TEST_DIR/.planning/history/runs.jsonl"

    # Should have exactly one line (one record)
    line_count=$(wc -l < "$TEST_DIR/.planning/history/runs.jsonl")
    [ "$line_count" -eq 1 ]
}

@test "history records correct task_id matching completed task" {
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    assert_file_exists "$TEST_DIR/.planning/history/runs.jsonl"

    # Extract task_id from the JSONL record
    recorded_task_id=$(python3 -c "
import json
with open('$TEST_DIR/.planning/history/runs.jsonl') as f:
    record = json.loads(f.readline())
    print(record['task_id'])
")
    [ "$recorded_task_id" = "1.1" ]
}

@test "history records iteration count from state file" {
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    assert_file_exists "$TEST_DIR/.planning/history/runs.jsonl"

    # Extract iterations from the JSONL record — should match state file iteration (3)
    recorded_iterations=$(python3 -c "
import json
with open('$TEST_DIR/.planning/history/runs.jsonl') as f:
    record = json.loads(f.readline())
    print(record['iterations'])
")
    [ "$recorded_iterations" = "3" ]
}

@test "history records duration calculated from started_at" {
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    assert_file_exists "$TEST_DIR/.planning/history/runs.jsonl"

    # Extract duration from the JSONL record — should be roughly 120 seconds
    # (started_at was set to 120 seconds ago in setup)
    recorded_duration=$(python3 -c "
import json
with open('$TEST_DIR/.planning/history/runs.jsonl') as f:
    record = json.loads(f.readline())
    print(record['duration_s'])
")
    # Duration should be >= 100 seconds (allowing for timing variance)
    # and < 300 seconds (sanity cap)
    python3 -c "
d = float('$recorded_duration')
assert 100 <= d < 300, f'duration {d} not in expected range 100-300'
"
}

@test "history records passed=true on successful transition" {
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    assert_file_exists "$TEST_DIR/.planning/history/runs.jsonl"

    recorded_passed=$(python3 -c "
import json
with open('$TEST_DIR/.planning/history/runs.jsonl') as f:
    record = json.loads(f.readline())
    print(record['passed'])
")
    [ "$recorded_passed" = "True" ]
}

@test "missing run_history.py does not break transition (non-blocking)" {
    # Temporarily hide run_history.py by renaming it
    if [ -f "$SCRIPTS_DIR/run_history.py" ]; then
        mv "$SCRIPTS_DIR/run_history.py" "$SCRIPTS_DIR/run_history.py.bak"
    fi

    run "$SCRIPTS_DIR/transition-task.sh"

    # Restore run_history.py
    if [ -f "$SCRIPTS_DIR/run_history.py.bak" ]; then
        mv "$SCRIPTS_DIR/run_history.py.bak" "$SCRIPTS_DIR/run_history.py"
    fi

    # Transition should still succeed even without run_history.py
    assert_success

    # stdout should contain next task JSON (1.2)
    echo "$output" | grep -q '"1.2"'
}
