#!/usr/bin/env bats
# Tests for scripts/transition-task.sh

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    mkdir -p "$TEST_DIR/.claude/plan/tasks"

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

    # Create state file pointing to task 1.1
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<'EOF'
---
session_id: "test-session"
task_id: "1.1"
iteration: 1
max_iterations: 5
project_dir: "/tmp/test"
---
EOF
    cd "$TEST_DIR"
}

teardown() {
    cd /
    rm -rf "$TEST_DIR"
}

@test "happy path: completes 1.1, returns next task 1.2 as JSON, exits 0" {
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success
    # stdout should contain JSON with task 1.2
    echo "$output" | grep -q '"id"'
    echo "$output" | grep -q '"1.2"'
}

@test "all tasks complete: single task plan, exits 2" {
    # Overwrite plan with a single-task plan
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
YAML
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_failure
    [ "$status" -eq 2 ]
}

@test "missing plan file exits 1" {
    rm "$TEST_DIR/.claude/plan/plan.yaml"
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_failure
    [ "$status" -eq 1 ]
    echo "$output" | grep -qi "plan file"
}

@test "missing state file exits 1" {
    rm "$TEST_DIR/.claude/verifier-loop.local.md"
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_failure
    [ "$status" -eq 1 ]
    echo "$output" | grep -qi "state file"
}

@test "no task_id in state exits 1" {
    # Overwrite state file with no task_id
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<'EOF'
---
session_id: "test-session"
iteration: 1
max_iterations: 5
project_dir: "/tmp/test"
---
EOF
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_failure
    [ "$status" -eq 1 ]
}

@test "integration check signal when phase has integration_check: true" {
    # Create plan with integration_check on the phase
    cat > "$TEST_DIR/.claude/plan/plan.yaml" <<'YAML'
metadata:
  project: "test-project"
  dev_server_command: "echo ok"
  dev_server_url: "http://localhost:3000"
  model_profile: "default"
phases:
  - id: 1
    name: "Phase 1"
    integration_check: true
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
  - id: 2
    name: "Phase 2"
    tasks:
      - id: "2.1"
        name: "Task C"
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
        prompt_file: "tasks/task-2.1.md"
YAML
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success
    # stderr should contain the integration check signal
    echo "$output" | grep -q "INTEGRATION_CHECK_NEEDED"
    # stdout JSON should have _integration_check_before
    echo "$output" | grep -q "_integration_check_before"
}
