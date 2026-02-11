#!/usr/bin/env bash
# common-setup.bash — shared bats test helper for gsd-vgl

# Resolve PLUGIN_ROOT to the project root (two levels up from test_helper/)
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
export PLUGIN_ROOT

SCRIPTS_DIR="${PLUGIN_ROOT}/scripts"
export SCRIPTS_DIR

HOOKS_DIR="${PLUGIN_ROOT}/hooks"
export HOOKS_DIR

# Load bats libraries from node_modules
BATS_LIB_DIR="${PLUGIN_ROOT}/node_modules"
load "${BATS_LIB_DIR}/bats-support/load.bash"
load "${BATS_LIB_DIR}/bats-assert/load.bash"
load "${BATS_LIB_DIR}/bats-file/load.bash"

# Creates a temporary test directory with .claude/plan/ structure
setup_test_dir() {
    TEST_DIR="$(mktemp -d)"
    export TEST_DIR
    mkdir -p "${TEST_DIR}/.claude/plan/tasks"
    create_sample_plan
}

# Cleans up the temporary test directory
teardown_test_dir() {
    if [[ -n "${TEST_DIR:-}" ]] && [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# Writes a minimal plan.yaml into TEST_DIR
create_sample_plan() {
    cat > "${TEST_DIR}/.claude/plan/plan.yaml" << 'YAML'
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
}

# Writes a minimal verifier-loop.local.md into TEST_DIR
create_sample_state() {
    cat > "${TEST_DIR}/.claude/verifier-loop.local.md" << 'STATE'
---
session_id: "test-session-001"
task_id: "1.1"
iteration: 1
max_iterations: 5
project_dir: "/tmp/test-project"
---

# Verifier Loop State
Active session for testing.
STATE
}
