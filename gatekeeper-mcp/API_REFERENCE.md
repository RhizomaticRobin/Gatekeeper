# Gatekeeper MCP API Reference

Complete documentation for all 13 MCP tools provided by the Gatekeeper MCP server.

## Table of Contents

- [Session Tools](#session-tools)
  - [create_session](#create_session)
  - [get_session](#get_session)
  - [close_session](#close_session)
- [Token Tools](#token-tools)
  - [submit_token](#submit_token)
  - [get_next_task](#get_next_task)
  - [get_token_status](#get_token_status)
- [Signal Tools](#signal-tools)
  - [record_agent_signal](#record_agent_signal)
  - [get_pending_signals](#get_pending_signals)
  - [mark_signal_processed](#mark_signal_processed)
- [Phase Gate Tools](#phase-gate-tools)
  - [submit_pvg_token](#submit_pvg_token)
  - [check_phase_integration](#check_phase_integration)
- [Evolution Tools](#evolution-tools)
  - [record_evolution_attempt](#record_evolution_attempt)
  - [get_evolution_context](#get_evolution_context)

---

## Session Tools

### create_session

Initialize a new verification loop session.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| session_id | string | Yes | - | Unique session identifier (format: `gk_YYYYMMDD_suffix`) |
| project_dir | string | Yes | - | Absolute path to project root directory |
| test_command | string | Yes | - | Shell command to run tests |
| task_id | string | No | null | Associated task ID (e.g., "2.1") |
| max_iterations | integer | No | 10 | Maximum verification loop iterations |
| plan_mode | boolean | No | false | Enable planning mode |
| verifier_model | string | No | "sonnet" | Verifier model to use |

**Returns:**

```json
{
    "session_id": "gk_20260223_a3f2c1",
    "project_dir": "/workspace/myproject",
    "test_command": "pytest tests/ -v",
    "task_id": "2.1",
    "max_iterations": 10,
    "plan_mode": false,
    "verifier_model": "sonnet",
    "active": true,
    "started_at": "2026-02-23T10:30:00.123456+00:00",
    "ended_at": null,
    "iteration": 0
}
```

**Errors:**

| Error | Description |
|-------|-------------|
| `ValueError` | Session ID already exists |
| `ValueError` | Required parameter missing or invalid |

**Example:**

```python
result = mcp.call_tool("create_session", {
    "session_id": "gk_20260223_a3f2c1",
    "project_dir": "/workspace/myproject",
    "test_command": "pytest tests/ -v",
    "task_id": "2.1",
    "max_iterations": 10
})
```

---

### get_session

Retrieve the current state of a session.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| session_id | string | Yes | - | Session identifier to retrieve |

**Returns:**

```json
{
    "session_id": "gk_20260223_a3f2c1",
    "project_dir": "/workspace/myproject",
    "test_command": "pytest tests/ -v",
    "task_id": "2.1",
    "max_iterations": 10,
    "plan_mode": false,
    "verifier_model": "sonnet",
    "active": true,
    "started_at": "2026-02-23T10:30:00.123456+00:00",
    "ended_at": null,
    "iteration": 3
}
```

**Errors:**

| Error | Description |
|-------|-------------|
| `ValueError` | Session not found |

**Example:**

```python
result = mcp.call_tool("get_session", {
    "session_id": "gk_20260223_a3f2c1"
})
print(f"Current iteration: {result['iteration']}")
```

---

### close_session

End an active session and mark it as inactive.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| session_id | string | Yes | - | Session identifier to close |

**Returns:**

```json
{
    "session_id": "gk_20260223_a3f2c1",
    "active": false,
    "started_at": "2026-02-23T10:30:00.123456+00:00",
    "ended_at": "2026-02-23T11:45:00.789012+00:00",
    "iteration": 5
}
```

**Errors:**

| Error | Description |
|-------|-------------|
| `ValueError` | Session not found |
| `ValueError` | Session already closed |

**Example:**

```python
result = mcp.call_tool("close_session", {
    "session_id": "gk_20260223_a3f2c1"
})
print(f"Session closed after {result['iteration']} iterations")
```

---

## Token Tools

### submit_token

Submit and validate a completion token.

**Token Formats:**
- `GK_COMPLETE_[a-f0-9]{32}` - Gatekeeper completion token
- `TQG_PASS_[a-f0-9]{32}` - Test quality gate pass token
- `TQG_FAIL_[a-f0-9]{32}` - Test quality gate failure token

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| token | string | Yes | - | Token value in valid format |
| session_id | string | Yes | - | Associated session ID |
| task_id | string | No | null | Associated task ID |

**Returns:**

```json
{
    "success": true,
    "token_type": "GK_COMPLETE",
    "token_value": "GK_COMPLETE_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "session_id": "gk_20260223_a3f2c1",
    "task_id": "2.1",
    "created_at": "2026-02-23T10:35:00.123456+00:00"
}
```

**Errors:**

| Error | Description |
|-------|-------------|
| `ValueError` | Invalid token format |
| `ValueError` | Token already exists (duplicate) |
| `ValueError` | Session not found |
| `ValueError` | Session not active |

**Side Effects:**
- Writes `.claude/verifier-loop.local.md` state file
- Writes `.claude/verifier-token.secret` state file

**Example:**

```python
import secrets

# Generate valid token
token = "GK_COMPLETE_" + secrets.token_hex(16)

result = mcp.call_tool("submit_token", {
    "token": token,
    "session_id": "gk_20260223_a3f2c1",
    "task_id": "2.1"
})
```

---

### get_next_task

Get the next action after token submission.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| session_id | string | Yes | - | Session identifier |

**Returns:**

```json
{
    "next_action": "CONTINUE",
    "iteration": 3,
    "max_iterations": 10,
    "has_tokens": true,
    "tokens_count": 2,
    "has_gk_complete": true,
    "has_tqg_pass": true,
    "max_reached": false,
    "message": "Verification token submitted, ready for verification check"
}
```

**next_action values:**

| Value | Description |
|-------|-------------|
| `CONTINUE` | Continue verification loop |
| `STOP_MAX_ITERATIONS` | Maximum iterations reached |
| `STOP_SUCCESS` | Verification passed, can stop |
| `STOP_SESSION_CLOSED` | Session was closed |

**Example:**

```python
result = mcp.call_tool("get_next_task", {
    "session_id": "gk_20260223_a3f2c1"
})

if result["next_action"] == "CONTINUE":
    print(f"Continue iteration {result['iteration']}")
```

---

### get_token_status

Query token status for a session.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| session_id | string | Yes | - | Session identifier |

**Returns:**

```json
{
    "session_id": "gk_20260223_a3f2c1",
    "total_count": 3,
    "tokens": [
        {
            "id": 1,
            "token_type": "GK_COMPLETE",
            "token_value": "GK_COMPLETE_aaa...",
            "task_id": "2.1",
            "created_at": "2026-02-23T10:30:00+00:00",
            "validated": true
        },
        {
            "id": 2,
            "token_type": "TQG_PASS",
            "token_value": "TQG_PASS_bbb...",
            "task_id": "2.1",
            "created_at": "2026-02-23T10:35:00+00:00",
            "validated": true
        }
    ],
    "by_type": {
        "GK_COMPLETE": 1,
        "TQG_PASS": 1,
        "TQG_FAIL": 0
    },
    "latest_token": {
        "id": 2,
        "token_type": "TQG_PASS",
        "token_value": "TQG_PASS_bbb...",
        "created_at": "2026-02-23T10:35:00+00:00"
    }
}
```

**Example:**

```python
result = mcp.call_tool("get_token_status", {
    "session_id": "gk_20260223_a3f2c1"
})
print(f"Total tokens: {result['total_count']}")
print(f"By type: {result['by_type']}")
```

---

## Signal Tools

### record_agent_signal

Record an agent signal for orchestrator processing.

**Signal Types:**

| Type | Description | Triggers State Write |
|------|-------------|---------------------|
| `TESTS_WRITTEN` | Tests have been written | No |
| `VERIFICATION_PASS` | Verification passed | Yes |
| `VERIFICATION_FAIL` | Verification failed | No |
| `IMPLEMENTATION_READY` | Implementation is ready | No |
| `ASSESSMENT_PASS` | Assessment passed | Yes |
| `ASSESSMENT_FAIL` | Assessment failed | No |
| `PHASE_ASSESSMENT_PASS` | Phase-level assessment passed | Yes |
| `PHASE_VERIFICATION_PASS` | Phase-level verification passed | Yes |

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| signal_type | string | Yes | - | Signal type from above |
| session_id | string | No | null | Associated session ID |
| task_id | string | No | null | Associated task ID |
| phase_id | integer | No | null | Associated phase ID |
| agent_id | string | No | null | Agent identifier |
| context | object | No | null | Additional context as JSON |

**Returns:**

```json
{
    "success": true,
    "signal_id": 42,
    "signal_type": "TESTS_WRITTEN",
    "session_id": "gk_20260223_a3f2c1",
    "task_id": "2.1",
    "phase_id": null,
    "agent_id": null,
    "pending": true,
    "created_at": "2026-02-23T10:40:00.123456+00:00"
}
```

**Errors:**

| Error | Description |
|-------|-------------|
| `ValueError` | Invalid signal type |

**Example:**

```python
result = mcp.call_tool("record_agent_signal", {
    "signal_type": "TESTS_WRITTEN",
    "session_id": "gk_20260223_a3f2c1",
    "task_id": "2.1",
    "context": {
        "files": ["test_example.py", "test_database.py"]
    }
})
print(f"Signal recorded with ID: {result['signal_id']}")
```

---

### get_pending_signals

Query signals waiting for processing.

**Important:** This tool does NOT automatically mark signals as processed. You must call `mark_signal_processed` explicitly.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| signal_type | string | No | null | Filter by signal type |
| session_id | string | No | null | Filter by session ID |
| task_id | string | No | null | Filter by task ID |
| phase_id | integer | No | null | Filter by phase ID |
| limit | integer | No | 100 | Maximum results |

**Returns:**

```json
{
    "count": 2,
    "signals": [
        {
            "signal_id": 42,
            "signal_type": "TESTS_WRITTEN",
            "session_id": "gk_20260223_a3f2c1",
            "task_id": "2.1",
            "phase_id": null,
            "agent_id": null,
            "pending": true,
            "created_at": "2026-02-23T10:40:00+00:00",
            "context_json": {"files": ["test_example.py"]}
        },
        {
            "signal_id": 43,
            "signal_type": "VERIFICATION_PASS",
            "session_id": "gk_20260223_a3f2c1",
            "task_id": "2.1",
            "phase_id": null,
            "agent_id": null,
            "pending": true,
            "created_at": "2026-02-23T10:45:00+00:00",
            "context_json": null
        }
    ],
    "filters_applied": {
        "signal_type": null,
        "session_id": null,
        "task_id": null,
        "phase_id": null
    }
}
```

**Example:**

```python
# Get all pending VERIFICATION_PASS signals
result = mcp.call_tool("get_pending_signals", {
    "signal_type": "VERIFICATION_PASS"
})

for signal in result["signals"]:
    print(f"Signal {signal['signal_id']}: {signal['signal_type']}")
```

---

### mark_signal_processed

Mark a signal as processed.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| signal_id | integer | Yes | - | Signal identifier to mark |

**Returns:**

```json
{
    "success": true,
    "signal_id": 42,
    "signal_type": "VERIFICATION_PASS",
    "pending": false,
    "processed_at": "2026-02-23T10:50:00.123456+00:00"
}
```

**Errors:**

| Error | Description |
|-------|-------------|
| `ValueError` | Signal not found |
| `ValueError` | Signal already processed |

**Side Effects:**
- Writes state files if signal is a completion signal type (VERIFICATION_PASS, ASSESSMENT_PASS, PHASE_ASSESSMENT_PASS, PHASE_VERIFICATION_PASS)

**Example:**

```python
# Mark signal as processed
result = mcp.call_tool("mark_signal_processed", {
    "signal_id": 42
})
print(f"Signal processed at: {result['processed_at']}")
```

---

## Phase Gate Tools

### submit_pvg_token

Submit a phase verification gate token.

**Token Format:** `PVG_COMPLETE_[a-f0-9]{32}`

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| session_id | string | Yes | - | Associated session ID |
| token_value | string | Yes | - | PVG token in valid format |
| phase_id | integer | Yes | - | Phase number (1, 2, 3, ...) |
| integration_check_passed | boolean | No | true | Whether integration check passed |

**Returns:**

```json
{
    "id": 1,
    "session_id": "gk_20260223_a3f2c1",
    "token_value": "PVG_COMPLETE_cccccccccccccccccccccccccccccccc",
    "phase_id": 3,
    "integration_check_passed": true,
    "created_at": "2026-02-23T11:00:00.123456+00:00",
    "validated": false
}
```

**Errors:**

| Error | Description |
|-------|-------------|
| `ValueError` | Invalid PVG token format |
| `ValueError` | Token already exists |

**Side Effects:**
- Writes state files

**Example:**

```python
import secrets

pvg_token = "PVG_COMPLETE_" + secrets.token_hex(16)

result = mcp.call_tool("submit_pvg_token", {
    "session_id": "gk_20260223_a3f2c1",
    "token_value": pvg_token,
    "phase_id": 3,
    "integration_check_passed": True
})
```

---

### check_phase_integration

Verify cross-phase artifact dependencies.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| phase_id | integer | Yes | - | Current phase number |
| required_artifacts | array | Yes | - | List of artifact paths to check |
| project_dir | string | No | null | Project directory for path resolution |

**Returns:**

```json
{
    "status": "PASS",
    "phase_id": 3,
    "details": [
        {
            "artifact": ".claude/plan/phases/phase-2.yaml",
            "full_path": "/workspace/myproject/.claude/plan/phases/phase-2.yaml",
            "exists": true
        },
        {
            "artifact": ".claude/plan/tasks/task-2.1.md",
            "full_path": "/workspace/myproject/.claude/plan/tasks/task-2.1.md",
            "exists": true
        }
    ],
    "missing_artifacts": [],
    "prior_phase_status": {
        "phase_id": 2,
        "completed": true,
        "integration_check_passed": true,
        "completed_at": "2026-02-23T10:00:00+00:00"
    },
    "checked_at": "2026-02-23T11:05:00.123456+00:00"
}
```

**status values:**

| Value | Description |
|-------|-------------|
| `PASS` | All artifacts exist |
| `NEEDS_FIXES` | Some artifacts missing |

**Example:**

```python
result = mcp.call_tool("check_phase_integration", {
    "phase_id": 3,
    "required_artifacts": [
        ".claude/plan/phases/phase-2.yaml",
        ".claude/plan/tasks/task-2.1.md"
    ],
    "project_dir": "/workspace/myproject"
})

if result["status"] == "PASS":
    print("All artifacts present")
else:
    print(f"Missing: {result['missing_artifacts']}")
```

---

## Evolution Tools

### record_evolution_attempt

Store an evolution or retry attempt with metrics.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| task_id | string | Yes | - | Task identifier (e.g., "2.1") |
| attempt_number | integer | Yes | - | Attempt number (1, 2, 3, ...) |
| outcome | string | Yes | - | Outcome: SUCCESS, FAILURE, or PARTIAL |
| metrics | object | No | null | Metrics dict (tests_passed, coverage_percent, etc.) |
| session_id | string | No | null | Associated session ID |

**Returns:**

```json
{
    "id": 1,
    "session_id": "gk_20260223_a3f2c1",
    "task_id": "2.1",
    "attempt_number": 1,
    "metrics_json": {
        "tests_passed": 10,
        "tests_failed": 2,
        "coverage_percent": 75.5,
        "errors": ["test_x.py::test_y failed"]
    },
    "outcome": "PARTIAL",
    "created_at": "2026-02-23T11:10:00.123456+00:00"
}
```

**Errors:**

| Error | Description |
|-------|-------------|
| `ValueError` | Invalid outcome (must be SUCCESS, FAILURE, or PARTIAL) |
| `ValueError` | Attempt number already exists for this task |

**Side Effects:**
- Writes state files if session_id provided

**Example:**

```python
result = mcp.call_tool("record_evolution_attempt", {
    "task_id": "2.1",
    "attempt_number": 1,
    "outcome": "FAILURE",
    "metrics": {
        "tests_passed": 8,
        "tests_failed": 4,
        "coverage_percent": 65.0,
        "errors": ["test_config.py failed", "test_database.py failed"]
    },
    "session_id": "gk_20260223_a3f2c1"
})
```

---

### get_evolution_context

Retrieve historical attempts for a task to inform retry strategy.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| task_id | string | Yes | - | Task identifier |
| include_metrics | boolean | No | true | Include full metrics in response |

**Returns:**

```json
{
    "task_id": "2.1",
    "total_attempts": 3,
    "attempts": [
        {
            "id": 1,
            "attempt_number": 1,
            "outcome": "FAILURE",
            "metrics_json": {"tests_passed": 8, "coverage_percent": 65.0},
            "created_at": "2026-02-23T11:10:00+00:00"
        },
        {
            "id": 2,
            "attempt_number": 2,
            "outcome": "PARTIAL",
            "metrics_json": {"tests_passed": 10, "coverage_percent": 75.5},
            "created_at": "2026-02-23T11:20:00+00:00"
        },
        {
            "id": 3,
            "attempt_number": 3,
            "outcome": "SUCCESS",
            "metrics_json": {"tests_passed": 12, "coverage_percent": 92.0},
            "created_at": "2026-02-23T11:30:00+00:00"
        }
    ],
    "best_attempt": {
        "attempt_number": 3,
        "outcome": "SUCCESS",
        "metrics": {"tests_passed": 12, "coverage_percent": 92.0},
        "created_at": "2026-02-23T11:30:00+00:00"
    },
    "summary": {
        "total_attempts": 3,
        "success_count": 1,
        "failure_count": 1,
        "partial_count": 1
    },
    "pattern": "IMPROVING",
    "retrieved_at": "2026-02-23T11:35:00.123456+00:00"
}
```

**pattern values:**

| Value | Description |
|-------|-------------|
| `IMPROVING` | Metrics improving across attempts |
| `DECLINING` | Metrics declining across attempts |
| `STABLE` | Metrics stable across attempts |
| `UNKNOWN` | Not enough data to determine pattern |

**Example:**

```python
result = mcp.call_tool("get_evolution_context", {
    "task_id": "2.1"
})

print(f"Total attempts: {result['total_attempts']}")
print(f"Pattern: {result['pattern']}")

if result['best_attempt']:
    print(f"Best: attempt #{result['best_attempt']['attempt_number']}")
    print(f"  Tests passed: {result['best_attempt']['metrics']['tests_passed']}")
    print(f"  Coverage: {result['best_attempt']['metrics']['coverage_percent']}%")
```

---

## Error Response Format

All tools return errors as JSON-RPC errors:

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "error": {
        "code": -32602,
        "message": "Invalid params",
        "data": "Invalid token format. Expected: GK_COMPLETE_[32 hex chars]"
    }
}
```

**Common error codes:**

| Code | Description |
|------|-------------|
| -32600 | Invalid Request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |

## Data Types

### Session

```json
{
    "session_id": "string",
    "project_dir": "string",
    "test_command": "string",
    "task_id": "string | null",
    "max_iterations": "integer",
    "plan_mode": "boolean",
    "verifier_model": "string",
    "active": "boolean",
    "started_at": "ISO 8601 timestamp",
    "ended_at": "ISO 8601 timestamp | null",
    "iteration": "integer"
}
```

### CompletionToken

```json
{
    "id": "integer",
    "session_id": "string",
    "token_type": "GK_COMPLETE | TQG_PASS | TQG_FAIL",
    "token_value": "string",
    "task_id": "string | null",
    "created_at": "ISO 8601 timestamp",
    "validated": "boolean"
}
```

### AgentSignal

```json
{
    "signal_id": "integer",
    "signal_type": "string",
    "session_id": "string | null",
    "task_id": "string | null",
    "phase_id": "integer | null",
    "agent_id": "string | null",
    "pending": "boolean",
    "context_json": "object | null",
    "created_at": "ISO 8601 timestamp",
    "processed_at": "ISO 8601 timestamp | null"
}
```

### PhaseToken

```json
{
    "id": "integer",
    "session_id": "string",
    "token_value": "string",
    "phase_id": "integer",
    "integration_check_passed": "boolean",
    "created_at": "ISO 8601 timestamp",
    "validated": "boolean"
}
```

### EvolutionAttempt

```json
{
    "id": "integer",
    "session_id": "string | null",
    "task_id": "string",
    "attempt_number": "integer",
    "metrics_json": "object | null",
    "outcome": "SUCCESS | FAILURE | PARTIAL",
    "created_at": "ISO 8601 timestamp"
}
```

## See Also

- [TOKEN_MCP_MIGRATION.md](TOKEN_MCP_MIGRATION.md) - Migration guide from bash scripts
- [README.md](README.md) - Quick start guide and overview
- `/workspace/craftium/docs/token-formats.md` - Token format specifications
