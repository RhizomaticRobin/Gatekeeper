# Token System Migration Guide: Bash Scripts to MCP

This guide shows how to migrate from the previous bash script-based token system to the new MCP-based approach.

## Overview

The Gatekeeper token system has been modernized to use the Model Context Protocol (MCP), providing:
- Centralized SQLite storage instead of file-based tokens
- Queryable token history and status
- Structured error handling
- Type-safe interfaces
- Backward compatibility with existing stop-hook.sh

## Migration Summary

| Old Approach | New Approach |
|--------------|--------------|
| Bash scripts (stop-hook.sh, fetch-completion-token.sh) | MCP server with Python tools |
| Token files in .claude/ directory | SQLite database at /tmp/gatekeeper.db |
| SHA-256 integrity checks in bash | Validation in MCP tools |
| Manual token generation | Tool-assisted token submission |
| Grep/awk for signal parsing | Structured signal queries |

## Step-by-Step Migration

### 1. Token Submission

**Before (Bash):**
```bash
# Generate token
TOKEN="GK_COMPLETE_$(openssl rand -hex 16)"

# Write to file
echo "$TOKEN" > .claude/verifier-token.secret

# Compute hash
TEST_CMD="pytest tests/"
TEST_CMD_B64=$(echo -n "$TEST_CMD" | base64)
TEST_CMD_HASH=$(echo -n "$TEST_CMD" | sha256sum | cut -d' ' -f1)

# Append to secret file
echo "$TEST_CMD_B64" >> .claude/verifier-token.secret
echo "$TEST_CMD_HASH" >> .claude/verifier-token.secret
```

**After (MCP):**
```python
# Single tool call handles everything
result = mcp.call_tool("submit_token", {
    "token": "GK_COMPLETE_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "session_id": "gk_20260223_a3f2c1",
    "task_id": "2.1"
})

# State files automatically generated
# verifier-loop.local.md and verifier-token.secret written by StateWriter
```

### 2. Session Management

**Before (Bash):**
```bash
# Create session file manually
cat > .claude/session.state << EOF
SESSION_ID=gk_20260223_a3f2c1
ITERATION=1
MAX_ITERATIONS=10
TEST_CMD=pytest tests/
EOF

# Track iteration in stop-hook
ITERATION=$((ITERATION + 1))
```

**After (MCP):**
```python
# Create session
session = mcp.call_tool("create_session", {
    "session_id": "gk_20260223_a3f2c1",
    "project_dir": "/workspace/myproject",
    "test_command": "pytest tests/ -v",
    "task_id": "2.1",
    "max_iterations": 10
})

# Get session state anytime
state = mcp.call_tool("get_session", {
    "session_id": "gk_20260223_a3f2c1"
})

# Close when done
mcp.call_tool("close_session", {
    "session_id": "gk_20260223_a3f2c1"
})
```

### 3. Signal Processing

**Before (Bash):**
```bash
# Write signal to file
echo "VERIFICATION_PASS" > .claude/signal.state
echo "TASK_ID=2.1" >> .claude/signal.state

# Parse signals in stop-hook
if grep -q "VERIFICATION_PASS" .claude/signal.state; then
    # Handle signal
fi
```

**After (MCP):**
```python
# Record signal
signal = mcp.call_tool("record_agent_signal", {
    "signal_type": "VERIFICATION_PASS",
    "session_id": "gk_20260223_a3f2c1",
    "task_id": "2.1"
})

# Query pending signals
pending = mcp.call_tool("get_pending_signals", {
    "signal_type": "VERIFICATION_PASS"
})

# Mark as processed
mcp.call_tool("mark_signal_processed", {
    "signal_id": signal["signal_id"]
})
```

### 4. Token Validation

**Before (Bash):**
```bash
# Read token from file
TOKEN=$(head -n1 .claude/verifier-token.secret)

# Validate format
if [[ ! "$TOKEN" =~ ^GK_COMPLETE_[a-f0-9]{32}$ ]]; then
    echo "Invalid token format"
    exit 1
fi

# Check hash
STORED_HASH=$(tail -n1 .claude/verifier-token.secret)
COMPUTED_HASH=$(echo -n "$TEST_CMD" | sha256sum | cut -d' ' -f1)
if [[ "$STORED_HASH" != "$COMPUTED_HASH" ]]; then
    echo "Hash mismatch"
    exit 1
fi
```

**After (MCP):**
```python
# Token is validated on submission
result = mcp.call_tool("submit_token", {
    "token": "GK_COMPLETE_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "session_id": "gk_20260223_a3f2c1"
})
# If call succeeds, token is valid

# Or check status explicitly
status = mcp.call_tool("get_token_status", {
    "session_id": "gk_20260223_a3f2c1"
})
```

### 5. Phase Verification

**Before (Bash):**
```bash
# Check phase file exists
if [[ -f ".claude/plan/phases/phase-2.yaml" ]]; then
    echo "Phase 2 artifacts exist"
fi

# Create PVG token manually
PVG_TOKEN="PVG_COMPLETE_$(openssl rand -hex 16)"
echo "$PVG_TOKEN" > .claude/phase-2.token
```

**After (MCP):**
```python
# Check phase integration
result = mcp.call_tool("check_phase_integration", {
    "phase_id": 3,
    "required_artifacts": [
        ".claude/plan/phases/phase-2.yaml",
        ".claude/plan/tasks/task-2.1.md"
    ],
    "project_dir": "/workspace/myproject"
})

# Submit PVG token
pvg = mcp.call_tool("submit_pvg_token", {
    "session_id": "gk_20260223_a3f2c1",
    "token_value": "PVG_COMPLETE_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "phase_id": 3,
    "integration_check_passed": result["status"] == "PASS"
})
```

### 6. Evolution Tracking

**Before (Bash):**
```bash
# Track attempts in files
ATTEMPT_FILE=".planning/evolution/2.1/attempt_1.json"
mkdir -p "$(dirname "$ATTEMPT_FILE")"
cat > "$ATTEMPT_FILE" << EOF
{
    "task_id": "2.1",
    "attempt_number": 1,
    "outcome": "FAILURE",
    "metrics": {
        "tests_passed": 8,
        "tests_failed": 4
    }
}
EOF
```

**After (MCP):**
```python
# Record attempt
attempt = mcp.call_tool("record_evolution_attempt", {
    "task_id": "2.1",
    "attempt_number": 1,
    "outcome": "FAILURE",
    "metrics": {
        "tests_passed": 8,
        "tests_failed": 4,
        "coverage_percent": 65.0
    }
})

# Get context for next attempt
context = mcp.call_tool("get_evolution_context", {
    "task_id": "2.1"
})
# Returns: {"total_attempts": 1, "attempts": [...], "pattern": "UNKNOWN", ...}
```

## Backward Compatibility

The MCP server maintains backward compatibility with `stop-hook.sh` by automatically writing state files:

### State Files Written by MCP

| File | Purpose | Written By |
|------|---------|------------|
| `.claude/verifier-loop.local.md` | Session state with YAML frontmatter | StateWriter after any state-changing operation |
| `.claude/verifier-token.secret` | Token, base64 test command, hash | StateWriter after token submission |

### stop-hook.sh Integration

The existing `stop-hook.sh` continues to work unchanged because:
1. MCP writes state files in the same format as before
2. File paths remain the same (`.claude/verifier-*`)
3. YAML frontmatter format preserved
4. SHA-256 hash computed correctly

```bash
# stop-hook.sh reads these files (unchanged)
source .claude/verifier-loop.local.md  # Parse frontmatter
read TOKEN < .claude/verifier-token.secret
```

## Migration Checklist

- [ ] Install gatekeeper-mcp package
- [ ] Update agent scripts to use MCP tools instead of bash
- [ ] Replace manual token file writes with `submit_token`
- [ ] Replace manual session files with `create_session`/`get_session`
- [ ] Replace signal file parsing with `record_agent_signal`/`get_pending_signals`
- [ ] Verify stop-hook.sh continues to work (it reads MCP-generated state files)
- [ ] Remove deprecated bash token scripts
- [ ] Update any custom scripts that parsed token files

## Common Migration Issues

### Issue: Token format validation errors

**Symptom:** `ValueError: Invalid token format`

**Solution:** Ensure tokens match expected format:
```python
# Correct format (32 lowercase hex chars)
import secrets
token = "GK_COMPLETE_" + secrets.token_hex(16)  # 16 bytes = 32 hex chars

# Wrong formats
token = "GK_COMPLETE_" + "abc"  # Too short
token = "GK_COMPLETE_" + "GHIJ"  # Not hex
token = "gk_complete_" + "abcd"  # Wrong case
```

### Issue: Session not found errors

**Symptom:** `ValueError: Session 'xxx' not found`

**Solution:** Create session before submitting tokens:
```python
# Create session first
mcp.call_tool("create_session", {
    "session_id": "gk_20260223_a3f2c1",
    "project_dir": "/workspace/myproject",
    "test_command": "pytest tests/"
})

# Then submit tokens
mcp.call_tool("submit_token", {
    "session_id": "gk_20260223_a3f2c1",  # Must match
    "token": "GK_COMPLETE_..."
})
```

### Issue: State files not generated

**Symptom:** `.claude/verifier-*` files not created

**Solution:** Ensure GK_SESSION_DIR is set correctly:
```bash
export GK_SESSION_DIR=/path/to/project/.claude
python -m gatekeeper_mcp.server_v3
```

### Issue: Signal not found

**Symptom:** `ValueError: Signal not found`

**Solution:** Verify signal_id exists and check if signal was already processed:
```python
# Check pending signals first
pending = mcp.call_tool("get_pending_signals", {
    "signal_type": "VERIFICATION_PASS"
})

# Verify signal is in the list before marking
signal_ids = [s["signal_id"] for s in pending["signals"]]
if signal_id in signal_ids:
    mcp.call_tool("mark_signal_processed", {"signal_id": signal_id})
```

### Issue: Duplicate token error

**Symptom:** `ValueError: Token '...' already exists`

**Solution:** Each token must be unique. Generate new tokens:
```python
import secrets

# Generate unique token each time
token = "GK_COMPLETE_" + secrets.token_hex(16)
```

## Getting Help

- See [API_REFERENCE.md](API_REFERENCE.md) for complete tool documentation
- See [README.md](README.md) for quick start guide
- Check the `/workspace/craftium/docs/token-formats.md` for token format specifications

## Key Benefits of MCP Migration

1. **Type Safety**: All parameters and returns are validated
2. **Queryability**: SQLite database enables complex queries
3. **Error Handling**: Clear error messages with context
4. **Structured Logging**: All operations logged with tool_name, session_id
5. **Atomic Operations**: State file writes use temp+rename pattern
6. **Testability**: Unit tests and integration tests for all tools
7. **Maintainability**: Python codebase easier to maintain than bash scripts
8. **Backward Compatible**: stop-hook.sh continues to work unchanged
