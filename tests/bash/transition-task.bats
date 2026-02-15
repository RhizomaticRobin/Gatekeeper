#!/usr/bin/env bats
# Tests for scripts/transition-task.sh

setup() {
    load 'test_helper/common-setup'
    TEST_DIR=$(mktemp -d)
    mkdir -p "$TEST_DIR/.claude/plan/tasks"

    # Test token for VGL completion gating
    TEST_TOKEN="VGL_COMPLETE_00000000000000000000000000000000"
    echo "$TEST_TOKEN" > "$TEST_DIR/.claude/verifier-token.secret"

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

# === Git Checkpoint Tests (Task 2.2) ===

@test "checkpoint: commit created after task completion" {
    # Initialize git repo in test dir
    git init "$TEST_DIR" >/dev/null 2>&1
    cd "$TEST_DIR"
    git config user.email "test@test.com"
    git config user.name "Test User"

    # Initial commit so HEAD exists
    git add -A
    git commit -m "initial" >/dev/null 2>&1

    # Modify plan.yaml so there's something to checkpoint (the completion changes status)
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    # Verify a checkpoint commit exists in git log
    run git log --oneline --all
    assert_output --partial "checkpoint(task-"
}

@test "checkpoint: commit message format matches checkpoint(task-{id}): {name}" {
    # Initialize git repo in test dir
    git init "$TEST_DIR" >/dev/null 2>&1
    cd "$TEST_DIR"
    git config user.email "test@test.com"
    git config user.name "Test User"

    # Initial commit
    git add -A
    git commit -m "initial" >/dev/null 2>&1

    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    # Get the most recent commit message
    LAST_MSG=$(cd "$TEST_DIR" && git log --format=%s -1)
    # Should match: checkpoint(task-1.1): Task A
    [[ "$LAST_MSG" =~ ^checkpoint\(task-1\.1\):\ .+ ]]
}

@test "checkpoint: skipped when not in git repo (no error)" {
    # TEST_DIR is NOT a git repo (setup() doesn't init git)
    cd "$TEST_DIR"
    run "$SCRIPTS_DIR/transition-task.sh"
    # Should still succeed (exit 0 with next task) — checkpoint skip is non-fatal
    assert_success
    # Output should contain the checkpoint skip warning
    assert_output --partial "not a git repository"
}

@test "checkpoint: skipped when no changes to commit" {
    # Initialize git repo
    git init "$TEST_DIR" >/dev/null 2>&1
    cd "$TEST_DIR"
    git config user.email "test@test.com"
    git config user.name "Test User"

    # Initial commit
    git add -A
    git commit -m "initial" >/dev/null 2>&1

    # Run transition once to create first checkpoint
    run "$SCRIPTS_DIR/transition-task.sh"
    assert_success

    # Now set up for a second run: update plan to have a new pending task, update state
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
      - id: "1.3"
        name: "Task C"
        status: "pending"
        depends_on:
          - "1.2"
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
    # Commit the plan so there are no staged changes
    git add -A
    git commit -m "setup for no-changes test" >/dev/null 2>&1

    # Update state to point to task 1.2
    cat > "$TEST_DIR/.claude/verifier-loop.local.md" <<'EOF'
---
session_id: "test-session"
task_id: "1.2"
iteration: 1
max_iterations: 5
project_dir: "/tmp/test"
---
EOF

    # Run transition — plan_utils will modify plan.yaml, so there WILL be changes
    # This test verifies that when git add finds no diff, it reports "no changes"
    # Actually, completing a task always modifies plan.yaml, so we need a different approach.
    # Let's pre-stage and commit the "completed" version of plan.yaml
    python3 "$SCRIPTS_DIR/plan_utils.py" "$TEST_DIR/.claude/plan/plan.yaml" --complete-task "1.2" --token "$TEST_TOKEN" >/dev/null
    git add -A
    git commit -m "pre-complete 1.2" >/dev/null 2>&1

    # Reset the task status back to pending in plan.yaml WITHOUT the git change
    # Actually, since plan_utils already changed the file on disk, the transition script
    # will run plan_utils again — but the file won't change because it's already completed.
    # So git add + git diff --cached --quiet will show no changes.

    run "$SCRIPTS_DIR/transition-task.sh"
    # Should succeed (next task found) or exit 2 (all complete)
    # The checkpoint should report "no changes"
    assert_output --partial "no changes"
}

@test "git dirty warning: cross-team-setup warns on uncommitted changes" {
    # Initialize git repo
    git init "$TEST_DIR" >/dev/null 2>&1
    cd "$TEST_DIR"
    git config user.email "test@test.com"
    git config user.name "Test User"

    # Initial commit
    git add -A
    git commit -m "initial" >/dev/null 2>&1

    # Create a dirty file (uncommitted change)
    echo "dirty" > "$TEST_DIR/dirty-file.txt"

    # Need to create validate-plan.py mock and get-unblocked-tasks.py mock
    # cross-team-setup.sh takes PLUGIN_ROOT as first arg
    # It calls validate-plan.py and get-unblocked-tasks.py
    # Create a mock PLUGIN_ROOT with simple mock scripts
    MOCK_PLUGIN="$TEST_DIR/mock-plugin"
    mkdir -p "$MOCK_PLUGIN/scripts"
    mkdir -p "$MOCK_PLUGIN/templates"

    # Mock validate-plan.py
    cat > "$MOCK_PLUGIN/scripts/validate-plan.py" <<'PYEOF'
import sys
print("Plan valid")
sys.exit(0)
PYEOF

    # Mock get-unblocked-tasks.py - return one task
    cat > "$MOCK_PLUGIN/scripts/get-unblocked-tasks.py" <<'PYEOF'
import sys, json
print(json.dumps([{"id": "1.1", "name": "Task A"}]))
PYEOF

    # Mock plan_utils.py
    cat > "$MOCK_PLUGIN/scripts/plan_utils.py" <<'PYEOF'
import yaml, sys
def load_plan(path):
    with open(path) as f:
        return yaml.safe_load(f)
def save_plan(path, plan):
    with open(path, 'w') as f:
        yaml.dump(plan, f)
def find_task(plan, task_id):
    for phase in plan.get('phases', []):
        for task in phase.get('tasks', []):
            if str(task['id']) == str(task_id):
                return phase, task
    return None, None
PYEOF

    # Mock opencode.json template
    echo '{}' > "$MOCK_PLUGIN/templates/opencode.json"

    run "$SCRIPTS_DIR/cross-team-setup.sh" "$MOCK_PLUGIN"
    # Output should contain the dirty warning
    assert_output --partial "uncommitted changes"
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
