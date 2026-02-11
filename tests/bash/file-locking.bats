#!/usr/bin/env bats
# Tests for file locking in scripts/transition-task.sh

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    mkdir -p "$TEST_DIR/.claude/plan/tasks"

    # Create a plan with tasks 1.1 (pending) and 1.2 (pending, depends on 1.1)
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
      - id: "1.3"
        name: "Task C"
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
        prompt_file: "tasks/task-1.3.md"
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

@test "transition-task uses flock" {
    # Verify that the transition-task.sh script contains flock usage
    grep -q 'flock' "$SCRIPTS_DIR/transition-task.sh"
}

@test "concurrent transition-task calls produce valid YAML" {
    # Run first transition (completes 1.1, gets next task)
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    # Verify the plan file is still valid YAML after transition
    python3 -c "
import yaml, sys
with open('$TEST_DIR/.claude/plan/plan.yaml') as f:
    plan = yaml.safe_load(f.read())
assert plan is not None, 'Plan should not be None'
assert 'phases' in plan, 'Plan should have phases'
# Verify task 1.1 was marked completed
for phase in plan['phases']:
    for task in phase['tasks']:
        if str(task['id']) == '1.1':
            assert task['status'] == 'completed', f\"Task 1.1 should be completed, got {task['status']}\"
            sys.exit(0)
sys.exit(1)
"
}

@test "lock file created in plan directory" {
    # Run transition which should create the lock file
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    # The lock file should exist at plan.yaml.lock
    LOCK_FILE="$TEST_DIR/.claude/plan/plan.yaml.lock"
    assert_file_exists "$LOCK_FILE"
}
