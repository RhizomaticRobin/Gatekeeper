# bats-core Research: Bash Script Testing for Gatekeeper

**Phase:** 01 - Testing & Stability
**Requirements:** R-002 (test shell scripts), R-003 (test hooks)
**Date:** 2026-02-11

---

## 1. Overview

[bats-core](https://github.com/bats-core/bats-core) (Bash Automated Testing System) is a
TAP-compliant testing framework for Bash 3.2+. It is the standard tool for unit-testing shell
scripts and is actively maintained (the successor to sstephenson/bats).

Key properties:
- Each `@test` block runs in its own subprocess (isolation by default).
- Uses Bash's `set -e` (errexit) internally: any non-zero exit code inside a test causes failure.
- Provides `run` helper to capture exit codes and output without aborting.
- Rich ecosystem of helper libraries: bats-support, bats-assert, bats-file.
- Produces TAP output, integrable with CI.

Official docs: https://bats-core.readthedocs.io/

---

## 2. Installation

### 2a. npm (recommended for this project)

```bash
# Project-local (preferred -- keeps version pinned)
npm install --save-dev bats

# Global
npm install -g bats
```

When installed locally, run via `npx bats` or `./node_modules/.bin/bats`.

### 2b. System package managers

```bash
# macOS
brew install bats-core

# Ubuntu/Debian
sudo apt-get install bats

# Arch
pacman -S bash-bats
```

Note: distro packages may lag behind; npm gives the latest release.

### 2c. Git submodule (vendored)

```bash
git submodule add https://github.com/bats-core/bats-core.git test/bats
git submodule add https://github.com/bats-core/bats-support.git test/test_helper/bats-support
git submodule add https://github.com/bats-core/bats-assert.git test/test_helper/bats-assert
git submodule add https://github.com/bats-core/bats-file.git test/test_helper/bats-file
```

Run via `./test/bats/bin/bats test/`.

### 2d. Recommendation for Gatekeeper

Use **npm** for bats-core itself (already a Claude Code plugin context) and **git submodules**
for the helper libraries (bats-support, bats-assert, bats-file). This avoids npm packages
that may not exist for the helpers while keeping the main runner easily updatable.

Alternative: install everything via npm if helper npm packages are available:
```bash
npm install --save-dev bats bats-support bats-assert
```

---

## 3. Test File Structure

### 3a. Directory layout

```
gatekeeper/
  hooks/
    stop-hook.sh
    guard-skills.sh
    post-cross.sh
  scripts/
    fetch-completion-token.sh
    setup-verifier-loop.sh
    generate-verifier-prompt.sh
    transition-task.sh
    cross-team-setup.sh
  test/
    bats/                          # bats-core (submodule or symlink)
    test_helper/
      bats-support/                # submodule
      bats-assert/                 # submodule
      bats-file/                   # submodule
      common-setup.bash            # shared setup for all test files
    fixtures/
      hook-input-stop.json         # sample hook inputs
      hook-input-guard.json
      state-file.md                # sample verifier-loop.local.md
      token-file.secret            # sample verifier-token.secret
    hooks/
      stop-hook.bats
      guard-skills.bats
      post-cross.bats
    scripts/
      fetch-completion-token.bats
      setup-verifier-loop.bats
      generate-verifier-prompt.bats
      transition-task.bats
```

### 3b. .bats file anatomy

```bash
#!/usr/bin/env bats

# Optional file-level tags
# bats file_tags=hooks

setup() {
    load '../test_helper/common-setup'
    _common_setup
}

teardown() {
    # Clean up temp files
    rm -rf "$TEST_TEMP_DIR"
}

@test "descriptive test name" {
    run some_command --with-args
    assert_success
    assert_output --partial "expected substring"
}

@test "another test" {
    run some_command --bad-args
    assert_failure
    assert_output --partial "ERROR"
}
```

### 3c. Common setup helper (test/test_helper/common-setup.bash)

```bash
_common_setup() {
    # Load assertion libraries
    load 'bats-support/load'
    load 'bats-assert/load'
    load 'bats-file/load'

    # Project root (two levels up from test_helper/)
    PROJECT_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." >/dev/null 2>&1 && pwd)"

    # Make scripts available on PATH
    PATH="$PROJECT_ROOT/scripts:$PROJECT_ROOT/hooks:$PATH"

    # Create a per-test temp directory
    TEST_TEMP_DIR="$(mktemp -d)"
    export TEST_TEMP_DIR
}
```

---

## 4. Key Assertions and Helpers

### 4a. bats-assert (https://github.com/bats-core/bats-assert)

| Function | Purpose | Example |
|---|---|---|
| `assert_success` | Exit code is 0 | `run cmd; assert_success` |
| `assert_failure` | Exit code is non-zero | `run cmd; assert_failure` |
| `assert_failure N` | Exit code is exactly N | `run cmd; assert_failure 2` |
| `assert_output "text"` | Exact stdout match | `assert_output "hello"` |
| `assert_output --partial "sub"` | Substring match | `assert_output --partial "ERROR"` |
| `assert_output --regexp "^pat"` | Regex match | `assert_output --regexp '^VGL_'` |
| `refute_output "text"` | Output does NOT match | `refute_output "secret_token"` |
| `assert_line "text"` | Any output line matches | `assert_line "iteration: 2"` |
| `assert_line --index N "text"` | Specific line matches | `assert_line --index 0 "OK"` |
| `assert_line --partial "sub"` | Any line contains substring | |
| `refute_line "text"` | No output line matches | |
| `assert_equal "actual" "expected"` | Two values are equal | |

### 4b. bats-file (https://github.com/bats-core/bats-file)

| Function | Purpose |
|---|---|
| `assert_file_exists` | File exists |
| `assert_file_not_exists` | File does not exist |
| `assert_dir_exists` | Directory exists |
| `assert_file_contains "path" "regex"` | File content matches regex |
| `assert_file_executable` | File has execute permission |
| `assert_file_permission "path" "644"` | Check permissions |
| `assert_files_equal "a" "b"` | Two files have same content |
| `assert_size_zero` | File is empty |
| `assert_symlink_to` | Symlink points to target |

### 4c. bats-core built-in variables

| Variable | Scope | Purpose |
|---|---|---|
| `$status` | After `run` | Exit code of last `run` |
| `$output` | After `run` | Combined stdout+stderr |
| `${lines[@]}` | After `run` | Output split into array |
| `$BATS_TEST_TMPDIR` | Per-test | Auto-cleaned temp dir |
| `$BATS_FILE_TMPDIR` | Per-file | Shared across tests in file |
| `$BATS_TEST_DIRNAME` | Per-test | Directory of .bats file |
| `$BATS_TEST_NAME` | Per-test | Function name of current test |
| `$BATS_TEST_DESCRIPTION` | Per-test | Description string |

### 4d. The `run` helper

```bash
# Basic usage -- captures exit code in $status, output in $output
run my_script.sh arg1 arg2

# Expect specific exit code (fails test if different)
run -0 my_script.sh       # expect success
run -1 my_script.sh       # expect exit code 1
run -2 my_script.sh       # expect exit code 2

# Expect failure (any non-zero)
run ! my_script.sh

# Keep empty lines in ${lines[@]}
run --keep-empty-lines my_script.sh

# Separate stderr into $stderr / ${stderr_lines[@]}
run --separate-stderr my_script.sh
```

**Critical:** `run` executes in a subshell. Variable mutations inside `run` do not propagate
back to the test. If you need side effects (file creation, env vars), either:
- Do not use `run` (let the command execute directly).
- Check side effects after `run` completes (e.g., check that a file was created).

---

## 5. Example Test Patterns for Gatekeeper

### 5a. Testing guard-skills.sh (hook that reads JSON from stdin, checks state file)

```bash
#!/usr/bin/env bats

setup() {
    load '../test_helper/common-setup'
    _common_setup

    # Create fake .claude directory structure
    WORK_DIR="$TEST_TEMP_DIR/project"
    mkdir -p "$WORK_DIR/.claude"
    cd "$WORK_DIR"
}

teardown() {
    rm -rf "$TEST_TEMP_DIR"
}

# --- No VGL active: all skills allowed ---

@test "guard-skills: allows any skill when no VGL is active" {
    # No state file exists
    INPUT='{"tool_input": {"skill": "quest"}}'
    run bash -c "echo '$INPUT' | $PROJECT_ROOT/hooks/guard-skills.sh"
    assert_success
}

# --- VGL active: blocked skills ---

@test "guard-skills: blocks /quest during active VGL" {
    touch .claude/verifier-loop.local.md
    INPUT='{"tool_input": {"skill": "quest"}}'
    run bash -c "echo '$INPUT' | $PROJECT_ROOT/hooks/guard-skills.sh"
    assert_failure 2
}

@test "guard-skills: blocks /bridge during active VGL" {
    touch .claude/verifier-loop.local.md
    INPUT='{"tool_input": {"skill": "bridge"}}'
    run bash -c "echo '$INPUT' | $PROJECT_ROOT/hooks/guard-skills.sh"
    assert_failure 2
}

# --- VGL active: allowed skills ---

@test "guard-skills: allows /cross-team during active VGL" {
    touch .claude/verifier-loop.local.md
    INPUT='{"tool_input": {"skill": "cross-team"}}'
    run bash -c "echo '$INPUT' | $PROJECT_ROOT/hooks/guard-skills.sh"
    assert_success
}

@test "guard-skills: allows /progress during active VGL" {
    touch .claude/verifier-loop.local.md
    INPUT='{"tool_input": {"skill": "progress"}}'
    run bash -c "echo '$INPUT' | $PROJECT_ROOT/hooks/guard-skills.sh"
    assert_success
}

@test "guard-skills: strips gatekeeper: prefix from skill name" {
    touch .claude/verifier-loop.local.md
    INPUT='{"tool_input": {"skill": "gatekeeper:quest"}}'
    run bash -c "echo '$INPUT' | $PROJECT_ROOT/hooks/guard-skills.sh"
    assert_failure 2
}

@test "guard-skills: allows non-gatekeeper skills during VGL" {
    touch .claude/verifier-loop.local.md
    INPUT='{"tool_input": {"skill": "some-other-plugin:thing"}}'
    run bash -c "echo '$INPUT' | $PROJECT_ROOT/hooks/guard-skills.sh"
    assert_success
}

@test "guard-skills: allows when no skill name in input" {
    touch .claude/verifier-loop.local.md
    INPUT='{"tool_input": {}}'
    run bash -c "echo '$INPUT' | $PROJECT_ROOT/hooks/guard-skills.sh"
    assert_success
}
```

### 5b. Testing stop-hook.sh (complex hook with JSON output)

```bash
#!/usr/bin/env bats

setup() {
    load '../test_helper/common-setup'
    _common_setup

    WORK_DIR="$TEST_TEMP_DIR/project"
    mkdir -p "$WORK_DIR/.claude"
    cd "$WORK_DIR"

    # Create a valid state file
    cat > .claude/verifier-loop.local.md <<'STATE'
---
active: true
session_id: "vgl_test_12345"
iteration: 1
max_iterations: 5
verification_criteria: |
  Tests must pass
test_command: "echo ok"
verifier_model: "opus"
project_dir: "."
---

This is the prompt text for the loop.
STATE

    # Create a valid token file
    VALID_TOKEN="VGL_COMPLETE_$(printf '%032x' 12345678901234567890)"
    echo "$VALID_TOKEN" > .claude/verifier-token.secret
    echo "TEST_CMD_B64:$(echo -n 'echo ok' | base64 -w0)" >> .claude/verifier-token.secret
    echo "TEST_CMD_HASH:$(echo -n 'echo ok' | sha256sum | cut -d' ' -f1)" >> .claude/verifier-token.secret
}

teardown() {
    rm -rf "$TEST_TEMP_DIR"
}

@test "stop-hook: exits cleanly when no state file exists" {
    rm -f .claude/verifier-loop.local.md
    HOOK_INPUT='{"transcript_path": "/dev/null"}'
    run bash -c "echo '$HOOK_INPUT' | $PROJECT_ROOT/hooks/stop-hook.sh"
    assert_success
}

@test "stop-hook: exits cleanly in team mode" {
    touch .claude/vgl-team-active
    HOOK_INPUT='{"transcript_path": "/dev/null"}'
    run bash -c "echo '$HOOK_INPUT' | $PROJECT_ROOT/hooks/stop-hook.sh"
    assert_success
}

@test "stop-hook: continues loop when token not found in transcript" {
    # Create transcript without token
    echo "Some agent output without completion token" > "$TEST_TEMP_DIR/transcript.txt"
    HOOK_INPUT="{\"transcript_path\": \"$TEST_TEMP_DIR/transcript.txt\"}"
    run bash -c "echo '$HOOK_INPUT' | $PROJECT_ROOT/hooks/stop-hook.sh"
    assert_success
    # Should output JSON with decision: block
    echo "$output" | jq -e '.decision == "block"'
}

@test "stop-hook: increments iteration on continue" {
    echo "Some agent output" > "$TEST_TEMP_DIR/transcript.txt"
    HOOK_INPUT="{\"transcript_path\": \"$TEST_TEMP_DIR/transcript.txt\"}"
    run bash -c "echo '$HOOK_INPUT' | $PROJECT_ROOT/hooks/stop-hook.sh"
    assert_success
    # State file should have iteration: 2
    grep 'iteration: 2' .claude/verifier-loop.local.md
}

@test "stop-hook: cleans up when max iterations reached" {
    # Set iteration to match max
    sed -i 's/iteration: 1/iteration: 5/' .claude/verifier-loop.local.md
    HOOK_INPUT='{"transcript_path": "/dev/null"}'
    run bash -c "echo '$HOOK_INPUT' | $PROJECT_ROOT/hooks/stop-hook.sh"
    assert_success
    # State files should be cleaned up
    [ ! -f .claude/verifier-loop.local.md ]
    [ ! -f .claude/verifier-token.secret ]
}
```

### 5c. Testing fetch-completion-token.sh (security-critical script)

```bash
#!/usr/bin/env bats

setup() {
    load '../test_helper/common-setup'
    _common_setup

    WORK_DIR="$TEST_TEMP_DIR/project"
    mkdir -p "$WORK_DIR/.claude"
    cd "$WORK_DIR"

    TOKEN="VGL_COMPLETE_aabbccdd11223344aabbccdd11223344"
    TEST_CMD="echo 'all tests pass'"
    TEST_CMD_B64=$(echo -n "$TEST_CMD" | base64 -w0)
    TEST_CMD_HASH=$(echo -n "$TEST_CMD" | sha256sum | cut -d' ' -f1)

    # Create state file
    cat > .claude/verifier-loop.local.md <<STATE
---
active: true
session_id: "vgl_test_1"
iteration: 1
max_iterations: 5
project_dir: "$WORK_DIR"
---

Test prompt.
STATE

    # Create token file
    cat > .claude/verifier-token.secret <<TOKENEOF
$TOKEN
TEST_CMD_B64:$TEST_CMD_B64
TEST_CMD_HASH:$TEST_CMD_HASH
TOKENEOF
}

teardown() {
    rm -rf "$TEST_TEMP_DIR"
}

@test "fetch-token: fails when no state file" {
    rm .claude/verifier-loop.local.md
    run "$PROJECT_ROOT/scripts/fetch-completion-token.sh" --session-dir .claude
    assert_failure
    assert_output --partial "No active VGL session"
}

@test "fetch-token: fails when no token file" {
    rm .claude/verifier-token.secret
    run "$PROJECT_ROOT/scripts/fetch-completion-token.sh" --session-dir .claude
    assert_failure
    assert_output --partial "Token file not found"
}

@test "fetch-token: grants token when tests pass" {
    run "$PROJECT_ROOT/scripts/fetch-completion-token.sh" --session-dir .claude
    assert_success
    assert_output --partial "VERIFICATION PASSED"
    assert_output --partial "<token-granted>"
    assert_output --partial "$TOKEN"
}

@test "fetch-token: denies token when tests fail" {
    # Override with a failing test command
    FAIL_CMD="exit 1"
    FAIL_B64=$(echo -n "$FAIL_CMD" | base64 -w0)
    FAIL_HASH=$(echo -n "$FAIL_CMD" | sha256sum | cut -d' ' -f1)
    cat > .claude/verifier-token.secret <<TOKENEOF
$TOKEN
TEST_CMD_B64:$FAIL_B64
TEST_CMD_HASH:$FAIL_HASH
TOKENEOF

    run "$PROJECT_ROOT/scripts/fetch-completion-token.sh" --session-dir .claude
    assert_failure
    assert_output --partial "VERIFICATION FAILED"
    assert_output --partial "<token-denied>"
    refute_output --partial "$TOKEN"
}

@test "fetch-token: detects hash tamper" {
    # Corrupt the hash
    sed -i 's/TEST_CMD_HASH:.*/TEST_CMD_HASH:0000000000000000/' .claude/verifier-token.secret
    run "$PROJECT_ROOT/scripts/fetch-completion-token.sh" --session-dir .claude
    assert_failure
    assert_output --partial "integrity check FAILED"
}
```

---

## 6. How to Mock External Commands

The scripts under test use: `jq`, `python3`, `base64`, `sha256sum`, `grep`, `sed`, `openssl`.

### 6a. PATH-based mocking (simple, no libraries needed)

Create a directory of mock scripts and prepend it to PATH:

```bash
setup() {
    load '../test_helper/common-setup'
    _common_setup

    # Create mock bin directory
    MOCK_BIN="$TEST_TEMP_DIR/mock-bin"
    mkdir -p "$MOCK_BIN"

    # Mock jq to return controlled output
    cat > "$MOCK_BIN/jq" <<'MOCK'
#!/bin/bash
# Return controlled JSON based on arguments
if [[ "$*" == *"transcript_path"* ]]; then
    echo "/tmp/fake-transcript.txt"
else
    echo "mock-jq-output"
fi
MOCK
    chmod +x "$MOCK_BIN/jq"

    # Mock python3 to avoid real Python calls
    cat > "$MOCK_BIN/python3" <<'MOCK'
#!/bin/bash
echo "mock-python-output"
MOCK
    chmod +x "$MOCK_BIN/python3"

    # Prepend mock bin to PATH (shadows real commands)
    PATH="$MOCK_BIN:$PATH"
}
```

### 6b. Function-based mocking (for sourced scripts)

If you source a script instead of executing it, you can override functions:

```bash
@test "mock a function" {
    # Override a function that would normally call an external tool
    parse_json() { echo "mocked_value"; }
    export -f parse_json

    source "$PROJECT_ROOT/scripts/my-script.sh"
    # ...assertions
}
```

**Caveat:** When mocking via exported functions, you must `unset -f func_name` in teardown
to prevent bleeding between tests (though bats runs each test in a subprocess, so this is
generally safe).

### 6c. bats-mock library (for complex stubbing)

```bash
# Install:
git submodule add https://github.com/jasonkarns/bats-mock.git test/test_helper/bats-mock

# Usage:
setup() {
    load '../test_helper/bats-mock/stub'
}

@test "mock jq" {
    stub jq \
        '-r .transcript_path : echo /tmp/transcript.txt' \
        '-r .tool_input.skill : echo quest'

    run my_hook.sh <<< '{"transcript_path":"/tmp/t.txt"}'

    assert_success
    unstub jq
}
```

### 6d. Recommendation for Gatekeeper

For most tests, **use real commands** (jq, python3, etc.) with controlled fixture data
rather than mocking. The scripts are integration-style -- they read files, call tools, and
produce output. Mocking every tool would make tests brittle and unrealistic.

**Mock only when:**
- A command has side effects you cannot control (e.g., `openssl rand`).
- A command is slow or unavailable in CI (e.g., a network call).
- You need deterministic output from a non-deterministic source.

For `openssl rand`, provide a PATH-based mock that returns a fixed hex string so that
tokens and session IDs are predictable in tests.

---

## 7. Testing JSON Output

Several hooks output JSON (decision: block/allow). Here is how to assert on JSON.

### 7a. Using jq in assertions

```bash
@test "hook returns valid JSON with decision=block" {
    run bash -c "echo '{}' | $PROJECT_ROOT/hooks/stop-hook.sh"
    assert_success

    # Parse JSON from output (may have mixed stderr/stdout)
    JSON_OUTPUT=$(echo "$output" | grep '^{' | tail -1)

    # Assert specific fields
    run jq -r '.decision' <<< "$JSON_OUTPUT"
    assert_output "block"

    run jq -r '.reason' <<< "$JSON_OUTPUT"
    assert_output --partial "prompt text"
}
```

### 7b. Helper function for JSON assertion

```bash
# In test_helper/common-setup.bash:
assert_json_field() {
    local json="$1"
    local field="$2"
    local expected="$3"
    local actual
    actual=$(echo "$json" | jq -r "$field")
    assert_equal "$actual" "$expected"
}

# Usage:
@test "hook returns correct JSON" {
    run my_hook.sh <<< "$INPUT"
    assert_success
    assert_json_field "$output" '.decision' 'block'
    assert_json_field "$output" '.reason' 'expected prompt'
}
```

### 7c. Validating JSON structure

```bash
@test "output is valid JSON" {
    run my_hook.sh <<< "$INPUT"
    # jq -e exits non-zero if input is not valid JSON
    echo "$output" | jq -e . > /dev/null
}

@test "JSON has required fields" {
    run my_hook.sh <<< "$INPUT"
    echo "$output" | jq -e '.decision' > /dev/null
    echo "$output" | jq -e '.reason' > /dev/null
}
```

### 7d. Handling mixed stdout/stderr

Hook scripts write debug info to stderr and JSON to stdout. Use `--separate-stderr`:

```bash
@test "hook JSON on stdout, debug on stderr" {
    run --separate-stderr bash -c "echo '$INPUT' | $PROJECT_ROOT/hooks/stop-hook.sh"
    assert_success

    # $output has stdout only (the JSON)
    echo "$output" | jq -e '.decision'

    # $stderr has debug/info messages
    # (only available with --separate-stderr)
}
```

---

## 8. Creating Fixture Data

### 8a. Fixture files in test/fixtures/

Pre-create representative data files that tests can copy into their temp directories:

```
test/fixtures/
    verifier-loop-active.md          # A valid state file with active loop
    verifier-loop-completed.md       # State file at max iterations
    verifier-token-valid.secret      # Valid token + test command
    verifier-token-corrupted.secret  # Corrupted hash for tamper detection
    hook-input-stop.json             # Sample stop hook stdin
    hook-input-guard-quest.json      # Guard hook input for /quest skill
    hook-input-guard-cross.json      # Guard hook input for /cross-team
    plan.yaml                        # Sample plan file
    transcript-with-token.txt        # Transcript containing completion token
    transcript-without-token.txt     # Transcript without token
```

### 8b. Fixture loading helper

```bash
# In test_helper/common-setup.bash:
FIXTURES_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../fixtures" && pwd)"

load_fixture() {
    local name="$1"
    local dest="${2:-.}"
    cp "$FIXTURES_DIR/$name" "$dest/"
}

# Usage in tests:
setup() {
    _common_setup
    cd "$TEST_TEMP_DIR"
    mkdir -p .claude
    load_fixture "verifier-loop-active.md" ".claude/verifier-loop.local.md"
    load_fixture "verifier-token-valid.secret" ".claude/verifier-token.secret"
}
```

### 8c. Dynamic fixture generation

For tests that need parameterized data:

```bash
create_state_file() {
    local iteration="${1:-1}"
    local max_iterations="${2:-5}"
    local session_id="${3:-vgl_test_1234}"
    local token="${4:-VGL_COMPLETE_aabbccdd11223344aabbccdd11223344}"

    cat > .claude/verifier-loop.local.md <<EOF
---
active: true
session_id: "$session_id"
iteration: $iteration
max_iterations: $max_iterations
test_command: "echo ok"
project_dir: "$(pwd)"
---

Test prompt for the verifier loop.
EOF

    echo "$token" > .claude/verifier-token.secret
    echo "TEST_CMD_B64:$(echo -n 'echo ok' | base64 -w0)" >> .claude/verifier-token.secret
    echo "TEST_CMD_HASH:$(echo -n 'echo ok' | sha256sum | cut -d' ' -f1)" >> .claude/verifier-token.secret
}

# Usage:
@test "stop-hook: exits at max iterations" {
    create_state_file 5 5   # iteration=5, max=5
    run bash -c "echo '{}' | stop-hook.sh"
    assert_success
    [ ! -f .claude/verifier-loop.local.md ]  # cleaned up
}
```

---

## 9. setup/teardown Patterns

### 9a. Lifecycle hierarchy

```
setup_suite()      -- once for entire test run (in setup_suite.bash)
  setup_file()     -- once per .bats file
    setup()        -- before each @test
      @test        -- the test itself
    teardown()     -- after each @test (even if test fails)
  teardown_file()  -- once per .bats file (even if tests fail)
teardown_suite()   -- once for entire test run
```

### 9b. Per-test isolation with temp directories

```bash
setup() {
    _common_setup
    # Use bats built-in temp dir (auto-cleaned)
    cd "$BATS_TEST_TMPDIR"
    mkdir -p .claude
}

# No teardown needed -- $BATS_TEST_TMPDIR is auto-cleaned by bats
```

### 9c. Expensive one-time setup

Use `setup_file` for operations that are slow but shared across tests:

```bash
setup_file() {
    load '../test_helper/common-setup'
    _common_setup

    # Build a complex fixture once
    export SHARED_PLAN_DIR="$BATS_FILE_TMPDIR/plan-project"
    mkdir -p "$SHARED_PLAN_DIR/.claude/plan"
    cp "$FIXTURES_DIR/plan.yaml" "$SHARED_PLAN_DIR/.claude/plan/"
}

setup() {
    load '../test_helper/common-setup'
    _common_setup

    # Each test gets a copy
    cp -r "$SHARED_PLAN_DIR" "$BATS_TEST_TMPDIR/project"
    cd "$BATS_TEST_TMPDIR/project"
}
```

---

## 10. Gotchas and Pitfalls

### 10a. set -e interaction

Bats uses `set -e` internally. Every command in a test that returns non-zero will fail the
test immediately. This is intentional -- it means bare assertions work:

```bash
@test "file was created" {
    run my_script.sh
    [ -f expected-output.txt ]   # Fails test if file missing (exit code 1)
}
```

**Problem:** Scripts under test that use `set -euo pipefail` may interact unexpectedly. The
script runs in a subshell via `run`, so its `set -e` is isolated. But if you source a script
directly (without `run`), its `set -e` becomes active in the test and can cause confusing
early exits.

**Solution:** Always use `run` to execute scripts under test. Only source helper functions.

### 10b. Negated commands and set -e

```bash
# WRONG -- Bash does not trigger set -e on negated commands:
@test "command fails" {
    ! my_command    # Does NOT fail the test even if my_command succeeds!
}

# CORRECT (bats 1.5+):
@test "command fails" {
    run ! my_command
    assert_failure
}

# CORRECT (older bats):
@test "command fails" {
    run my_command
    [ "$status" -ne 0 ]
}
```

### 10c. Pipes with run

```bash
# WRONG -- pipe is parsed OUTSIDE of run:
run echo "hello" | grep "hello"
# This actually does: (run echo "hello") | grep "hello"

# CORRECT options:

# Option 1: wrap in bash -c
run bash -c 'echo "hello" | grep "hello"'

# Option 2: use bats_pipe (bats 1.10+)
run bats_pipe echo "hello" \| grep "hello"

# Option 3: wrap in a function
my_pipe() { echo "hello" | grep "hello"; }
run my_pipe
```

### 10d. Variable mutations in run

```bash
# WRONG -- variable changes inside run do not propagate:
@test "sets variable" {
    run bash -c 'MY_VAR=hello'
    [ "$MY_VAR" = "hello" ]   # FAILS -- MY_VAR is still unset
}

# CORRECT -- check side effects (files, output) instead:
@test "creates output file" {
    run my_script.sh
    assert_success
    [ -f output.txt ]                    # File was created (side effect)
    assert_file_contains output.txt "expected"
}
```

### 10e. Stdin piping to scripts under test

Many of the Gatekeeper hooks read from stdin (`INPUT=$(cat)`). To pipe data:

```bash
# Option 1: bash -c with echo
run bash -c "echo '{\"key\":\"value\"}' | $PROJECT_ROOT/hooks/guard-skills.sh"

# Option 2: heredoc via bash -c
run bash -c "$PROJECT_ROOT/hooks/guard-skills.sh <<'EOF'
{\"key\": \"value\"}
EOF"

# Option 3: use a fixture file
run bash -c "cat $FIXTURES_DIR/input.json | $PROJECT_ROOT/hooks/guard-skills.sh"

# Option 4: redirect from file
run bash -c "$PROJECT_ROOT/hooks/guard-skills.sh < $FIXTURES_DIR/input.json"
```

### 10f. [[ ]] vs [ ] on macOS Bash 3.2

On macOS with Bash 3.2, `[[ ]]` and `(( ))` do not trigger `set -e` correctly. Use `[ ]`
or append `|| false` for portable tests:

```bash
# Portable:
[ "$status" -eq 0 ]

# Or with || false:
[[ "$status" -eq 0 ]] || false
```

Since this project likely targets Linux CI, this is less of a concern but worth knowing.

### 10g. File descriptor 3

Bats uses fd 3 internally for TAP output. If a script under test opens background processes,
close fd 3 explicitly to prevent hangs:

```bash
run bash -c "my_background_script.sh 3>&-"
```

### 10h. load vs source

- `load` appends `.bash` extension automatically and resolves relative to the test file.
- `source` works with any extension but requires a full or relative path.
- Use `load` for bats helpers; use `source` for `.sh` files if needed.

### 10i. Each test file evaluated n+1 times

Bats evaluates each test file n+1 times (once to count tests, then once per test). Any code
at the top level of the file (outside setup/teardown/@test) will execute n+1 times. Keep
top-level code minimal -- just `load` statements and variable declarations.

---

## 11. Running Tests

### 11a. Basic execution

```bash
# Single file
npx bats test/hooks/guard-skills.bats

# All tests in directory
npx bats test/

# Recursive
npx bats -r test/

# With TAP output
npx bats --formatter tap test/

# Pretty output (default)
npx bats --formatter pretty test/

# Filter by test name regex
npx bats --filter "guard-skills" test/

# Filter by tags
npx bats --filter-tags "hooks" test/
```

### 11b. Parallel execution

```bash
# Run tests in parallel (uses all cores)
npx bats --jobs 4 test/

# Note: parallel mode requires tests to be truly independent
# (no shared state outside of test temp dirs)
```

### 11c. CI integration

```bash
# In CI pipeline (e.g., GitHub Actions):
npx bats --formatter tap test/ | tee test-results.tap

# Or with JUnit output for CI integration:
npx bats --formatter junit test/ > test-results.xml
```

---

## 12. Scripts Inventory and Testing Priority

| Script | Type | Complexity | Dependencies | Priority |
|---|---|---|---|---|
| `hooks/guard-skills.sh` | Hook | Low | jq | HIGH -- simple, good first test target |
| `hooks/post-cross.sh` | Hook | Medium | jq, python3, sed | MEDIUM |
| `hooks/stop-hook.sh` | Hook | High | jq, python3, grep, sed, awk | HIGH -- core loop logic |
| `scripts/fetch-completion-token.sh` | Script | Medium | base64, sha256sum, sed, grep | HIGH -- security critical |
| `scripts/setup-verifier-loop.sh` | Script | High | jq, python3, openssl, base64, sha256sum | HIGH -- session setup |
| `scripts/generate-verifier-prompt.sh` | Script | Medium | python3, sed | MEDIUM |
| `scripts/transition-task.sh` | Script | Medium | python3, sed, grep | MEDIUM |
| `scripts/cross-team-setup.sh` | Script | High | python3, jq | LOW -- integration test territory |

**Recommended approach:** Start with `guard-skills.sh` (simplest), then `fetch-completion-token.sh`
(security critical, well-isolated), then `stop-hook.sh` (complex but most important).

---

## 13. References

- [bats-core GitHub](https://github.com/bats-core/bats-core)
- [bats-core official docs](https://bats-core.readthedocs.io/)
- [Writing tests](https://bats-core.readthedocs.io/en/stable/writing-tests.html)
- [Gotchas](https://bats-core.readthedocs.io/en/stable/gotchas.html)
- [Tutorial](https://bats-core.readthedocs.io/en/stable/tutorial.html)
- [Installation](https://bats-core.readthedocs.io/en/stable/installation.html)
- [bats-assert](https://github.com/bats-core/bats-assert)
- [bats-file](https://github.com/bats-core/bats-file)
- [bats-mock](https://github.com/jasonkarns/bats-mock)
- [Testing Bash Scripts with BATS (HackerOne)](https://www.hackerone.com/blog/testing-bash-scripts-bats-practical-guide)
- [Getting Started with Bash Testing (stefanzweifel)](https://stefanzweifel.dev/posts/2020/12/22/getting-started-with-bash-testing-with-bats/)
- [Testing Bash Scripts with BATS (Baeldung)](https://www.baeldung.com/linux/testing-bash-scripts-bats)
