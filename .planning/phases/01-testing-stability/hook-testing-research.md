# Hook Testing Research -- Gatekeeper

Phase 1: Testing & Stability | Requirements: R-003, R-005
Researched: 2026-02-11

---

## 1. Overview of the Claude Code Hook Contract

Claude Code hooks are shell commands (or LLM prompts) that fire at specific
lifecycle points. For command hooks the contract is:

```
Claude Code --[JSON on stdin]--> Hook Script --[exit code + stdout JSON + stderr]--> Claude Code
```

### Common Input Fields (all events)

Every hook receives these fields via stdin as a JSON object:

| Field             | Type   | Description                                    |
|-------------------|--------|------------------------------------------------|
| `session_id`      | string | Current session identifier                     |
| `transcript_path` | string | Path to conversation JSONL transcript          |
| `cwd`             | string | Working directory when the hook is invoked     |
| `permission_mode` | string | One of: default, plan, acceptEdits, dontAsk, bypassPermissions |
| `hook_event_name` | string | Name of the event that fired                   |

### Exit Code Contract

| Exit Code | Meaning            | stdout Handling                        | stderr Handling                    |
|-----------|--------------------|----------------------------------------|------------------------------------|
| 0         | Success/allow      | Parsed as JSON (decision fields read)  | Shown in verbose mode only         |
| 2         | Blocking error     | **Ignored entirely**                   | Fed back to Claude as error text   |
| Other     | Non-blocking error  | Ignored                                | Shown in verbose mode only         |

**Critical rule**: JSON output is ONLY processed on exit 0. If you exit 2 and
print JSON to stdout, Claude Code ignores it completely. Use stderr for the
blocking message instead.

### JSON Output Fields (exit 0 only)

| Field            | Default | Description                                              |
|------------------|---------|----------------------------------------------------------|
| `continue`       | true    | false = halt Claude entirely (overrides all decisions)   |
| `stopReason`     | none    | Message shown to user when continue=false                |
| `suppressOutput` | false   | true = hide stdout from verbose mode                     |
| `systemMessage`  | none    | Warning message shown to the user                        |

Sources:
- [Hooks Reference -- Claude Code Docs](https://code.claude.com/docs/en/hooks)
- [Anthropic plugin-dev SKILL.md](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/hook-development/SKILL.md)

---

## 2. Gatekeeper Hook Inventory

From `/home/user/gatekeeper/hooks/hooks.json`:

| Event       | Matcher      | Script                | Purpose                                  |
|-------------|-------------|-----------------------|------------------------------------------|
| Stop        | (none/all)  | `stop-hook.sh`        | Gatekeeper loop control -- block stop or transition |
| PreToolUse  | `Skill`     | `guard-skills.sh`     | Block disruptive skills during Gatekeeper loop   |
| PostToolUse | `Skill`     | `post-cross.sh`       | Show pipeline progress after /cross-team  |
| PostToolUse | `Write\|Edit` | `intel-index.js`    | Index file exports/imports on code changes |

---

## 3. Testing Stop Hooks

### Contract for Stop Event

**Input (stdin JSON):**
```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/home/user/project",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}
```

The `stop_hook_active` field is `true` when Claude is already continuing due to
a prior Stop hook block. This prevents infinite loops.

**Output (stdout JSON on exit 0):**
```json
{
  "decision": "block",
  "reason": "Prompt text to send back to Claude as its next instruction",
  "systemMessage": "Short status message shown to user"
}
```

To allow Claude to stop: exit 0 with no JSON, or omit the `decision` field.

### Testing `stop-hook.sh` Specifically

The stop hook has complex conditional logic depending on filesystem state:

1. **No state file** -> exits 0 (allow stop)
2. **Team mode active** (`.claude/gk-team-active` exists) -> exits 0
3. **State file exists, token matches** -> exits 0 (cleanup + optionally auto-transition)
4. **State file exists, token does not match** -> exits 0 with `decision: "block"` (continue loop)
5. **State file corrupted** -> exits 0 (cleanup + allow stop)
6. **Max iterations reached** -> exits 0 (cleanup + allow stop)

#### Test Harness for Stop Hook

```bash
#!/bin/bash
# test-stop-hook.sh -- Test harness for stop-hook.sh

HOOK_SCRIPT="$(dirname "$0")/../../hooks/stop-hook.sh"
FIXTURES_DIR="$(dirname "$0")/fixtures/stop"
PASS=0
FAIL=0

# Helper: run hook with fixture input, capture stdout/stderr/exit
run_hook() {
  local fixture_file="$1"
  local test_dir="$2"

  # Run hook in test directory context, piping fixture JSON as stdin
  cd "$test_dir"
  STDOUT=$(cat "$fixture_file" | bash "$HOOK_SCRIPT" 2>/tmp/hook-stderr)
  EXIT_CODE=$?
  STDERR=$(cat /tmp/hook-stderr)
  cd - >/dev/null
}

assert_exit() {
  local expected="$1"
  local label="$2"
  if [[ "$EXIT_CODE" -eq "$expected" ]]; then
    echo "  PASS: exit code = $expected ($label)"
    ((PASS++))
  else
    echo "  FAIL: exit code = $EXIT_CODE, expected $expected ($label)"
    ((FAIL++))
  fi
}

assert_json_field() {
  local field="$1"
  local expected="$2"
  local label="$3"
  local actual
  actual=$(echo "$STDOUT" | jq -r "$field" 2>/dev/null)
  if [[ "$actual" == "$expected" ]]; then
    echo "  PASS: $field = '$expected' ($label)"
    ((PASS++))
  else
    echo "  FAIL: $field = '$actual', expected '$expected' ($label)"
    ((FAIL++))
  fi
}

assert_no_json() {
  local label="$1"
  if [[ -z "$STDOUT" ]] || ! echo "$STDOUT" | jq . >/dev/null 2>&1; then
    echo "  PASS: no JSON output ($label)"
    ((PASS++))
  else
    echo "  FAIL: unexpected JSON output: $STDOUT ($label)"
    ((FAIL++))
  fi
}

# --- Test: No state file -> allow stop ---
echo "Test: No state file"
TEST_DIR=$(mktemp -d)
run_hook "$FIXTURES_DIR/basic-stop-input.json" "$TEST_DIR"
assert_exit 0 "should exit 0"
assert_no_json "should produce no JSON"
rm -rf "$TEST_DIR"

# --- Test: Active loop, no token match -> block stop ---
echo "Test: Active loop, continue"
TEST_DIR=$(mktemp -d)
mkdir -p "$TEST_DIR/.claude"
# Create state file with frontmatter
cat > "$TEST_DIR/.claude/verifier-loop.local.md" << 'STATE'
---
iteration: 1
max_iterations: 5
session_id: "test-session"
---
Your task prompt goes here.
STATE
# Create token file
echo "GK_COMPLETE_00000000000000000000000000000000" > "$TEST_DIR/.claude/verifier-token.secret"
# Create a dummy transcript with NO token
echo '{"type":"text"}' > /tmp/test-transcript.jsonl
# Build fixture with transcript path
cat > /tmp/test-stop-input.json << EOF
{
  "session_id": "test-session",
  "transcript_path": "/tmp/test-transcript.jsonl",
  "cwd": "$TEST_DIR",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}
EOF
run_hook /tmp/test-stop-input.json "$TEST_DIR"
assert_exit 0 "should exit 0"
assert_json_field '.decision' 'block' "should block stop"
rm -rf "$TEST_DIR"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
```

### Key Assertions for Stop Hooks

| Scenario                       | Expected Exit | Expected JSON                        |
|-------------------------------|--------------|--------------------------------------|
| No state file                 | 0            | (empty/none)                         |
| Team mode active              | 0            | (empty/none)                         |
| Loop active, token mismatch   | 0            | `{"decision":"block","reason":"..."}`|
| Loop active, token matches    | 0            | (empty/none) -- cleanup done         |
| Max iterations reached        | 0            | (empty/none) -- cleanup done         |
| Corrupted state               | 0            | (empty/none) -- cleanup done         |

---

## 4. Testing PreToolUse Hooks

### Contract for PreToolUse Event

**Input (stdin JSON):**
```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/home/user/project",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Skill",
  "tool_input": {
    "skill": "gatekeeper:quest",
    "args": ""
  },
  "tool_use_id": "toolu_01ABC123"
}
```

**Decision output (exit 0 with JSON):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow|deny|ask",
    "permissionDecisionReason": "Explanation"
  }
}
```

**Blocking shortcut (exit 2):**
- Exit code 2 blocks the tool call
- stderr text is fed back to Claude as the error message
- stdout is ignored

### Testing `guard-skills.sh` Specifically

The guard-skills hook has this decision tree:

1. No skill name in input -> exit 0 (allow)
2. No Gatekeeper state file -> exit 0 (allow, not in loop)
3. Skill is "cross" or "cross-team" -> exit 0 (allowed during loop)
4. Skill is "progress" -> exit 0 (allowed during loop)
5. Skill is on blocklist (quest, bridge, run-away, etc.) -> exit 2 (block)
6. Not a gatekeeper skill -> exit 0 (allow)

#### Example Test Cases

```bash
# Test: Block /quest during active loop
echo "Test: Block /quest during active Gatekeeper loop"
TEST_DIR=$(mktemp -d)
mkdir -p "$TEST_DIR/.claude"
cat > "$TEST_DIR/.claude/verifier-loop.local.md" << 'EOF'
---
iteration: 1
max_iterations: 5
session_id: "test"
---
Test prompt
EOF

FIXTURE='{"tool_name":"Skill","tool_input":{"skill":"gatekeeper:quest"},"hook_event_name":"PreToolUse"}'
cd "$TEST_DIR"
STDOUT=$(echo "$FIXTURE" | bash "$HOOK_SCRIPT" 2>/tmp/hook-stderr)
EXIT_CODE=$?
STDERR=$(cat /tmp/hook-stderr)
cd - >/dev/null

assert_exit 2 "should block with exit 2"
# stderr should contain the blocking message
[[ "$STDERR" == *"BLOCKED"* ]] && echo "  PASS: stderr contains BLOCKED" || echo "  FAIL: stderr missing BLOCKED"

# Test: Allow /cross-team during active loop
echo "Test: Allow /cross-team during active Gatekeeper loop"
FIXTURE='{"tool_name":"Skill","tool_input":{"skill":"gatekeeper:cross-team"},"hook_event_name":"PreToolUse"}'
cd "$TEST_DIR"
STDOUT=$(echo "$FIXTURE" | bash "$HOOK_SCRIPT" 2>/tmp/hook-stderr)
EXIT_CODE=$?
cd - >/dev/null
assert_exit 0 "should allow with exit 0"

# Test: Allow any skill when no Gatekeeper loop active
echo "Test: Allow /quest when no Gatekeeper loop"
TEST_DIR2=$(mktemp -d)
FIXTURE='{"tool_name":"Skill","tool_input":{"skill":"gatekeeper:quest"},"hook_event_name":"PreToolUse"}'
cd "$TEST_DIR2"
STDOUT=$(echo "$FIXTURE" | bash "$HOOK_SCRIPT" 2>/dev/null)
EXIT_CODE=$?
cd - >/dev/null
assert_exit 0 "should allow with exit 0 (no loop)"

rm -rf "$TEST_DIR" "$TEST_DIR2"
```

### Key Assertions for PreToolUse Hooks

| Scenario                         | Expected Exit | stderr Contains        |
|---------------------------------|--------------|------------------------|
| No skill name                    | 0            | (empty)                |
| No Gatekeeper loop active               | 0            | (empty)                |
| Gatekeeper active + /quest              | 2            | "BLOCKED"              |
| Gatekeeper active + /bridge             | 2            | "BLOCKED"              |
| Gatekeeper active + /run-away           | 2            | "BLOCKED"              |
| Gatekeeper active + /cross-team         | 0            | (empty)                |
| Gatekeeper active + /progress           | 0            | (empty)                |
| Gatekeeper active + non-gatekeeper skill   | 0            | (empty)                |

---

## 5. Testing PostToolUse Hooks

### Contract for PostToolUse Event

**Input (stdin JSON):**
```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/home/user/project",
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",
  "tool_name": "Skill",
  "tool_input": {
    "skill": "gatekeeper:cross-team",
    "args": ""
  },
  "tool_response": { "success": true },
  "tool_use_id": "toolu_01ABC123"
}
```

PostToolUse hooks are informational -- they **cannot block** the tool call
(it already ran). Exit 2 shows stderr to Claude but does not undo anything.

**Output patterns:**
- Exit 0 with text stdout: shown in verbose mode (transcript)
- Exit 0 with JSON `systemMessage`: shown as warning to user
- Exit 0 with JSON `decision: "block"` + `reason`: prompts Claude with feedback

### Testing `post-cross.sh` Specifically

This hook:
1. Checks if the skill was /cross or /cross-team -> exit 0 if not
2. Checks for Gatekeeper state file -> exit 0 if not present
3. Checks for plan file -> exit 0 if not present
4. Reads current task from state, computes pipeline status
5. Prints progress banner to stdout

The output is plain text (not JSON), shown in verbose mode.

```bash
# Test: Non-cross skill -> early exit, no output
echo "Test: Non-cross skill ignored"
FIXTURE='{"tool_name":"Skill","tool_input":{"skill":"gatekeeper:quest"},"hook_event_name":"PostToolUse"}'
STDOUT=$(echo "$FIXTURE" | bash "$HOOK_SCRIPT" 2>/dev/null)
EXIT_CODE=$?
assert_exit 0 "should exit 0"
[[ -z "$STDOUT" ]] && echo "  PASS: no output" || echo "  FAIL: unexpected output"
```

### Testing `intel-index.js` Specifically

This Node.js hook reads stdin JSON, extracts file path, and indexes
exports/imports. It also supports a query mode.

```bash
# Test: Index a Write event for a .ts file
FIXTURE='{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/tmp/test-index/src/utils.ts",
    "content": "export function add(a: number, b: number) { return a + b; }\nimport { config } from \"./config\";"
  },
  "hook_event_name": "PostToolUse"
}'

# Need .planning/intel/ to exist (opt-in check)
mkdir -p /tmp/test-index/.planning/intel
cd /tmp/test-index
echo "$FIXTURE" | node /path/to/hooks/intel-index.js
EXIT_CODE=$?
assert_exit 0 "should exit 0"

# Verify index.json was created
[[ -f .planning/intel/index.json ]] && echo "  PASS: index.json created" || echo "  FAIL: no index.json"

# Verify the file entry exists
jq -e '.files["/tmp/test-index/src/utils.ts"]' .planning/intel/index.json >/dev/null 2>&1 && \
  echo "  PASS: file entry exists" || echo "  FAIL: file entry missing"

# Test: Query mode (hotspots)
QUERY='{"action":"query","type":"hotspots","limit":3}'
RESULT=$(echo "$QUERY" | node /path/to/hooks/intel-index.js)
echo "$RESULT" | jq -e '.query == "hotspots"' >/dev/null 2>&1 && \
  echo "  PASS: query response valid" || echo "  FAIL: query response invalid"

cd -
rm -rf /tmp/test-index
```

---

## 6. Example Test Harness

### Recommended Approach: Plain Bash with Helpers

Given the hook scripts are bash (and one Node.js), a plain bash test runner
with jq assertions is the simplest and most portable approach. No external
framework needed.

```bash
#!/bin/bash
# tests/hooks/run-hook-tests.sh
# Minimal test harness for hook scripts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOKS_DIR="$REPO_ROOT/hooks"

PASS=0
FAIL=0
ERRORS=()

# --- Test Helpers ---

# Run a hook script with JSON piped to stdin
# Sets: STDOUT, STDERR, EXIT_CODE
run_hook() {
  local hook_script="$1"
  local input_json="$2"
  local work_dir="${3:-.}"

  local stderr_file
  stderr_file=$(mktemp)

  cd "$work_dir"
  set +e
  STDOUT=$(echo "$input_json" | bash "$hook_script" 2>"$stderr_file")
  EXIT_CODE=$?
  set -e
  STDERR=$(cat "$stderr_file")
  rm -f "$stderr_file"
  cd - >/dev/null 2>&1
}

# Run a Node.js hook with JSON piped to stdin
run_node_hook() {
  local hook_script="$1"
  local input_json="$2"
  local work_dir="${3:-.}"

  local stderr_file
  stderr_file=$(mktemp)

  cd "$work_dir"
  set +e
  STDOUT=$(echo "$input_json" | node "$hook_script" 2>"$stderr_file")
  EXIT_CODE=$?
  set -e
  STDERR=$(cat "$stderr_file")
  rm -f "$stderr_file"
  cd - >/dev/null 2>&1
}

assert_exit_code() {
  local expected="$1"
  local label="$2"
  if [[ "$EXIT_CODE" -eq "$expected" ]]; then
    echo "  PASS: exit=$expected | $label"
    ((PASS++))
  else
    echo "  FAIL: exit=$EXIT_CODE (expected $expected) | $label"
    ((FAIL++))
    ERRORS+=("$label: exit=$EXIT_CODE expected=$expected")
  fi
}

assert_stdout_json() {
  local jq_filter="$1"
  local expected="$2"
  local label="$3"
  local actual
  actual=$(echo "$STDOUT" | jq -r "$jq_filter" 2>/dev/null || echo "__JQ_ERROR__")
  if [[ "$actual" == "$expected" ]]; then
    echo "  PASS: $jq_filter='$expected' | $label"
    ((PASS++))
  else
    echo "  FAIL: $jq_filter='$actual' (expected '$expected') | $label"
    ((FAIL++))
    ERRORS+=("$label: $jq_filter='$actual' expected='$expected'")
  fi
}

assert_stdout_empty() {
  local label="$1"
  if [[ -z "$STDOUT" ]]; then
    echo "  PASS: stdout empty | $label"
    ((PASS++))
  else
    echo "  FAIL: stdout not empty: '${STDOUT:0:80}...' | $label"
    ((FAIL++))
    ERRORS+=("$label: stdout not empty")
  fi
}

assert_stderr_contains() {
  local pattern="$1"
  local label="$2"
  if echo "$STDERR" | grep -q "$pattern"; then
    echo "  PASS: stderr contains '$pattern' | $label"
    ((PASS++))
  else
    echo "  FAIL: stderr missing '$pattern' | $label"
    ((FAIL++))
    ERRORS+=("$label: stderr missing '$pattern'")
  fi
}

assert_file_exists() {
  local filepath="$1"
  local label="$2"
  if [[ -f "$filepath" ]]; then
    echo "  PASS: file exists | $label"
    ((PASS++))
  else
    echo "  FAIL: file missing: $filepath | $label"
    ((FAIL++))
    ERRORS+=("$label: file missing $filepath")
  fi
}

# Create a temporary test directory with optional Gatekeeper state
setup_gk_dir() {
  local dir
  dir=$(mktemp -d)
  mkdir -p "$dir/.claude"
  echo "$dir"
}

teardown_dir() {
  rm -rf "$1"
}

# --- Run Tests ---
echo "=== Hook Tests ==="
echo ""

# Source individual test files
for test_file in "$SCRIPT_DIR"/test-*.sh; do
  if [[ -f "$test_file" ]]; then
    echo "--- $(basename "$test_file") ---"
    source "$test_file"
    echo ""
  fi
done

# --- Summary ---
echo "==============================="
echo "Results: $PASS passed, $FAIL failed"
if [[ ${#ERRORS[@]} -gt 0 ]]; then
  echo ""
  echo "Failures:"
  for err in "${ERRORS[@]}"; do
    echo "  - $err"
  done
fi
echo "==============================="

[[ $FAIL -eq 0 ]]
```

### Alternative: BATS Framework

If the project adopts bats-core, tests look like this:

```bash
#!/usr/bin/env bats
# tests/hooks/guard-skills.bats

setup() {
  HOOK="$BATS_TEST_DIRNAME/../../hooks/guard-skills.sh"
  TEST_DIR=$(mktemp -d)
  mkdir -p "$TEST_DIR/.claude"
}

teardown() {
  rm -rf "$TEST_DIR"
}

@test "allow skill when no Gatekeeper loop active" {
  cd "$TEST_DIR"
  run bash -c 'echo "{\"tool_name\":\"Skill\",\"tool_input\":{\"skill\":\"quest\"}}" | bash '"$HOOK"
  [ "$status" -eq 0 ]
}

@test "block /quest during active Gatekeeper loop" {
  # Create Gatekeeper state file
  cat > "$TEST_DIR/.claude/verifier-loop.local.md" << 'EOF'
---
iteration: 1
max_iterations: 5
session_id: "test"
---
Test prompt
EOF
  cd "$TEST_DIR"
  run bash -c 'echo "{\"tool_name\":\"Skill\",\"tool_input\":{\"skill\":\"gatekeeper:quest\"}}" | bash '"$HOOK"
  [ "$status" -eq 2 ]
  [[ "$output" == *"BLOCKED"* ]]
}

@test "allow /cross-team during active Gatekeeper loop" {
  cat > "$TEST_DIR/.claude/verifier-loop.local.md" << 'EOF'
---
iteration: 1
max_iterations: 5
session_id: "test"
---
Test prompt
EOF
  cd "$TEST_DIR"
  run bash -c 'echo "{\"tool_name\":\"Skill\",\"tool_input\":{\"skill\":\"gatekeeper:cross-team\"}}" | bash '"$HOOK"
  [ "$status" -eq 0 ]
}
```

**BATS gotcha with pipes**: `run echo "..." | bash script` does NOT work.
Bash parses the pipe outside of `run`, so `run` only captures `echo`. Use
`run bash -c '... | ...'` instead. See
[bats-core gotchas](https://bats-core.readthedocs.io/en/stable/gotchas.html).

---

## 7. Creating Realistic Fixture Data

### Strategy: Capture Real Invocations

Add a logger hook that dumps the actual JSON Claude Code sends:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "cat > /tmp/hook-capture-$(date +%s%N).json"
        }]
      }
    ]
  }
}
```

Then copy the captured files to `tests/hooks/fixtures/` as reference data.

### Fixture Templates

#### Stop Event Fixture

```json
{
  "session_id": "sess_test_001",
  "transcript_path": "{{TRANSCRIPT_PATH}}",
  "cwd": "{{CWD}}",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}
```

#### PreToolUse (Skill) Fixture

```json
{
  "session_id": "sess_test_001",
  "transcript_path": "/tmp/test-transcript.jsonl",
  "cwd": "{{CWD}}",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Skill",
  "tool_input": {
    "skill": "{{SKILL_NAME}}",
    "args": ""
  },
  "tool_use_id": "toolu_test_001"
}
```

#### PostToolUse (Write) Fixture

```json
{
  "session_id": "sess_test_001",
  "transcript_path": "/tmp/test-transcript.jsonl",
  "cwd": "{{CWD}}",
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",
  "tool_name": "Write",
  "tool_input": {
    "file_path": "{{FILE_PATH}}",
    "content": "{{CONTENT}}"
  },
  "tool_response": {
    "filePath": "{{FILE_PATH}}",
    "success": true
  },
  "tool_use_id": "toolu_test_002"
}
```

### Fixture Generation Helper

```bash
# Generate a fixture by interpolating template variables
generate_fixture() {
  local template="$1"
  shift
  local result="$template"
  while [[ $# -ge 2 ]]; do
    local key="$1"
    local value="$2"
    result="${result//\{\{$key\}\}/$value}"
    shift 2
  done
  echo "$result"
}

# Usage:
FIXTURE=$(generate_fixture "$PRETOOLUSE_TEMPLATE" \
  "CWD" "/tmp/testdir" \
  "SKILL_NAME" "gatekeeper:quest")
```

---

## 8. Gotchas and Pitfalls

### 8.1 stdin Buffering and `cat` vs Line-by-Line Reading

All four Gatekeeper hooks use one of two patterns:

- **Bash hooks**: `INPUT=$(cat)` -- reads all of stdin into a variable at once
- **Node.js hook**: `process.stdin.on('data', chunk => ...)` -- event-driven

**Gotcha**: If you forget to consume stdin, jq will hang waiting for input.
Always pipe the complete JSON string before the script starts.

```bash
# CORRECT: echo pipes complete JSON, then stdin closes
echo '{"tool_name":"Skill"}' | bash hook.sh

# WRONG: heredoc with missing terminator will hang
bash hook.sh << 'EOF'
{"tool_name":"Skill"}
```

**Gotcha**: `cat` in a subshell with `set -e` can cause issues if stdin is
empty or the pipe breaks. The hooks handle this correctly by reading into a
variable first.

### 8.2 `set -euo pipefail` Interactions

`stop-hook.sh` uses `set -euo pipefail`. This means:

- **`-e`**: Any command returning non-zero exits the script immediately
- **`-u`**: Unset variables cause immediate exit
- **`-o pipefail`**: Pipe failure propagates (e.g., `grep | sed` fails if grep fails)

**Testing impact:**

```bash
# This WILL fail with set -e if grep finds nothing:
EXTRACTED=$(grep -oP 'pattern' file)  # exit 1 if no match -> script exits!

# The stop-hook works around this by checking file existence first,
# and by using || to catch grep failures.

# When testing, you must ensure the test environment matches expectations.
# Missing files or empty variables trigger -eu exits.
```

**Gotcha with `set -e` in test harness**: If your test harness also uses
`set -e`, a failing assertion will abort the entire test run. Wrap hook
invocations with `set +e` / `set -e`:

```bash
set +e
STDOUT=$(echo "$FIXTURE" | bash "$HOOK_SCRIPT" 2>/tmp/stderr)
EXIT_CODE=$?
set -e
```

### 8.3 Exit Code Semantics

| Code | Claude Code Interpretation               | Common Mistake                           |
|------|------------------------------------------|------------------------------------------|
| 0    | Success, read stdout JSON                | Forgetting to output JSON when you need to block |
| 2    | Block (stderr -> Claude)                 | Printing JSON to stdout (it's ignored!)  |
| 1    | Non-blocking error (ignored)             | Using exit 1 to "block" (it won't)       |

**The stop-hook uses exit 0 + JSON `decision: "block"` for loop continuation.**
It never uses exit 2. This is correct for Stop hooks where the blocking
mechanism is the JSON decision field, not the exit code.

**The guard-skills hook uses exit 2 to block.** This is the correct PreToolUse
pattern for a simple "deny" without needing JSON output.

### 8.4 Working Directory Dependencies

All four hooks depend on relative paths (`.claude/verifier-loop.local.md`,
`.claude/plan/plan.yaml`, etc.). Tests **must** `cd` into a properly set up
temporary directory before running the hook.

```bash
# WRONG: running from repo root, hook reads repo's .claude/ files
echo "$FIXTURE" | bash hooks/stop-hook.sh

# CORRECT: cd to isolated test directory
cd "$TEST_DIR"
echo "$FIXTURE" | bash "$REPO_ROOT/hooks/stop-hook.sh"
cd -
```

### 8.5 jq Dependency

All bash hooks use `jq` for JSON parsing. Tests must ensure `jq` is available.
The `intel-index.js` hook uses Node.js's built-in `JSON.parse()`.

### 8.6 External Dependencies in stop-hook.sh

The stop hook calls external scripts during plan-mode auto-transition:
- `${PLUGIN_ROOT}/scripts/transition-task.sh`
- `${PLUGIN_ROOT}/scripts/setup-verifier-loop.sh`
- `python3` with `plan_utils` module

For unit tests, these should be mocked or the test should focus on the
pre-transition paths. Integration tests can exercise the full transition
path with real plan files.

### 8.7 Transcript File Requirements

The stop hook reads the transcript file to search for completion tokens:
```bash
EXTRACTED_TOKEN=$(grep --no-filename -oP 'GK_COMPLETE_[a-f0-9]{32}' "$TRANSCRIPT_PATH")
```

Tests must provide a real file at the `transcript_path` specified in the
fixture JSON. An empty file or a file with specific token strings controls
the test outcome.

### 8.8 Shell Profile stdout Interference

Claude Code documentation warns: "If your shell profile prints text on startup,
it can interfere with JSON parsing." When testing, ensure hooks are run with a
clean environment or use `env -i bash` to avoid profile-sourced output mixing
with JSON.

### 8.9 Race Conditions with Temp Files

The stop hook creates temp files (`${STATE_FILE}.tmp.$$`) during iteration
updates. Parallel test execution could theoretically conflict. Use isolated
`TEST_DIR` per test case.

### 8.10 BATS-Specific Pipe Gotcha

In bats-core, `run command | other` is parsed as `(run command) | other`, NOT
as `run (command | other)`. The `run` only captures the first command.

```bash
# WRONG - run captures echo, not the piped result
run echo '{}' | bash hook.sh

# CORRECT - wrap in bash -c
run bash -c 'echo "{}" | bash hook.sh'

# ALSO CORRECT - use a function
my_hook_runner() { echo '{}' | bash hook.sh; }
run my_hook_runner
```

---

## 9. Recommended Test Plan for Gatekeeper Hooks

### Priority Order

1. **guard-skills.sh** (PreToolUse) -- Simplest, most critical for security
   - 8 test cases covering the decision tree
   - Pure stdin/exit-code testing, no filesystem complexity
   - Only needs `.claude/verifier-loop.local.md` presence/absence

2. **stop-hook.sh** (Stop) -- Most complex, highest risk
   - 10+ test cases covering all branches
   - Requires filesystem setup (state file, token file, transcript file)
   - Mock external scripts for unit tests
   - Separate integration tests for auto-transition

3. **post-cross.sh** (PostToolUse) -- Medium complexity
   - 5 test cases (early exits + pipeline display)
   - Requires plan.yaml and state file setup
   - Output is plain text, assert on string patterns

4. **intel-index.js** (PostToolUse) -- Node.js, different test approach
   - Test with `node` instead of `bash`
   - Requires `.planning/intel/` directory (opt-in check)
   - Test both Write/Edit indexing and query mode
   - Assert on created index.json content

### Test File Structure

```
tests/
  hooks/
    run-hook-tests.sh          # Main test runner
    test-guard-skills.sh       # PreToolUse guard tests
    test-stop-hook.sh          # Stop hook tests
    test-post-cross.sh         # PostToolUse cross tests
    test-intel-index.sh        # PostToolUse intel tests
    fixtures/
      stop/
        basic-stop-input.json
        active-loop-input.json
      pretooluse/
        skill-quest.json
        skill-cross-team.json
        skill-unknown.json
      posttooluse/
        write-ts-file.json
        edit-ts-file.json
        skill-cross.json
```

### CI Integration

```bash
# Run all hook tests (add to CI pipeline)
bash tests/hooks/run-hook-tests.sh

# Prerequisites: jq, node, bash 4+
which jq node bash || { echo "Missing dependencies"; exit 1; }
```

---

## 10. References

- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) -- Official documentation with complete JSON schemas
- [Claude Code Hook Development SKILL.md](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/hook-development/SKILL.md) -- Anthropic's plugin hook development guide
- [Claude Code Hooks Blog Post](https://claude.com/blog/how-to-configure-hooks) -- Practical configuration walkthrough
- [bats-core Writing Tests](https://bats-core.readthedocs.io/en/stable/writing-tests.html) -- BATS test authoring guide
- [bats-core Gotchas](https://bats-core.readthedocs.io/en/stable/gotchas.html) -- Pipe and run command pitfalls
- [bats-assert](https://github.com/bats-core/bats-assert) -- Common assertion helpers for BATS
- [disler/claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery) -- Community hook examples with logging-based testing
- [karanb192/claude-code-hooks](https://github.com/karanb192/claude-code-hooks) -- Collection of hook patterns
- [ChrisWiles/claude-code-showcase](https://github.com/ChrisWiles/claude-code-showcase) -- Comprehensive plugin configuration example
- [set -euo pipefail Explained](https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425) -- Shell safety modes and their side effects
- [DataCamp Claude Code Hooks Tutorial](https://www.datacamp.com/tutorial/claude-code-hooks) -- Practical hook automation guide
