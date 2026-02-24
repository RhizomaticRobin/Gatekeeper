# Gatekeeper MCP Server

Centralized token submission and validation system for the Gatekeeper verification loop.

## Overview

The Gatekeeper MCP Server provides a unified Model Context Protocol (MCP) interface for:
- Session lifecycle management
- Token submission and validation (GK_COMPLETE, TQG_PASS, TQG_FAIL, PVG_COMPLETE)
- Agent signal recording and processing
- Phase verification gate management
- Evolution and retry attempt tracking

This replaces the previous scattered approach of bash scripts and file-based tokens with a clean, queryable SQLite-backed API.

## Architecture

```
                    +-------------------+
                    |   MCP Client      |
                    |  (Claude Code)    |
                    +--------+----------+
                             |
                             | JSON-RPC
                             v
+--------------------------------------------------+
|               Gatekeeper MCP Server              |
|  +------------+  +------------+  +-------------+ |
|  |  Sessions  |  |   Tokens   |  |   Signals   | |
|  +------------+  +------------+  +-------------+ |
|  +------------+  +------------+  +-------------+ |
|  | PhaseGates |  | Evolution  |  | StateWriter | |
|  +------------+  +------------+  +-------------+ |
|                     |                            |
|          +----------+----------+                |
|          |    SQLite Database   |                |
|          +----------------------+                |
+------------------------|-------------------------+
                         |
                         | State Files
                         v
          +------------------------------+
          |  .claude/verifier-loop.local.md |
          |  .claude/verifier-token.secret  |
          +------------------------------+
                         |
                         | Read by
                         v
          +------------------------------+
          |      stop-hook.sh            |
          +------------------------------+
```

## Installation

```bash
cd /workspace/craftium/gatekeeper-mcp
pip install -e .
```

### With Development Dependencies

```bash
pip install -e ".[dev]"
```

## Configuration

Configuration is managed via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `GK_DB_PATH` | SQLite database path | `/tmp/gatekeeper.db` |
| `GK_SESSION_DIR` | Session state directory | `/tmp/gatekeeper-sessions` |
| `GK_LOG_LEVEL` | Logging level | `INFO` |

## Quick Start

### 1. Start the MCP Server

```bash
# Using Python module
cd /workspace/craftium/gatekeeper-mcp
python -m gatekeeper_mcp.server_v3

# Or with custom configuration
GK_DB_PATH=/path/to/db.sqlite \
GK_SESSION_DIR=/path/to/sessions \
python -m gatekeeper_mcp.server_v3
```

### 2. Create a Session

```python
# Via MCP tool call
result = mcp.call_tool("create_session", {
    "session_id": "gk_20260223_a3f2c1",
    "project_dir": "/workspace/myproject",
    "test_command": "pytest tests/ -v",
    "task_id": "2.1",
    "max_iterations": 10,
    "plan_mode": False
})
# Returns: {"session_id": "gk_20260223_a3f2c1", "active": True, ...}
```

### 3. Submit a Token

```python
result = mcp.call_tool("submit_token", {
    "token": "GK_COMPLETE_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "session_id": "gk_20260223_a3f2c1",
    "task_id": "2.1"
})
# Returns: {"success": True, "token_type": "GK_COMPLETE", ...}
```

### 4. Record Agent Signals

```python
result = mcp.call_tool("record_agent_signal", {
    "signal_type": "TESTS_WRITTEN",
    "session_id": "gk_20260223_a3f2c1",
    "task_id": "2.1",
    "context": {"files": ["test_example.py"]}
})
# Returns: {"signal_id": 1, "pending": True, ...}
```

## Tool Reference

### Session Tools

#### create_session

Initialize a new verification loop session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| session_id | string | Yes | Unique session identifier (e.g., "gk_20260223_a3f2c1") |
| project_dir | string | Yes | Project root directory path |
| test_command | string | Yes | Command to run tests |
| task_id | string | No | Associated task ID |
| max_iterations | integer | No | Maximum loop iterations (default: 10) |
| plan_mode | boolean | No | Enable plan mode (default: false) |
| verifier_model | string | No | Verifier model (default: "sonnet") |

**Returns:** Session object with fields: session_id, project_dir, test_command, task_id, max_iterations, plan_mode, active, started_at, iteration

**Example:**
```python
session = create_session(
    session_id="gk_20260223_a3f2c1",
    project_dir="/workspace/myproject",
    test_command="pytest tests/ -v",
    task_id="2.1",
    max_iterations=10
)
# Returns: {
#     "session_id": "gk_20260223_a3f2c1",
#     "project_dir": "/workspace/myproject",
#     "test_command": "pytest tests/ -v",
#     "task_id": "2.1",
#     "max_iterations": 10,
#     "active": true,
#     "started_at": "2026-02-23T10:30:00+00:00",
#     "iteration": 1
# }
```

#### get_session

Retrieve session state.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| session_id | string | Yes | Session identifier |

**Returns:** Session object

**Example:**
```python
session = get_session(session_id="gk_20260223_a3f2c1")
# Returns: {"session_id": "gk_20260223_a3f2c1", "active": True, ...}
```

#### close_session

End an active session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| session_id | string | Yes | Session identifier |

**Returns:** Session object with active=false and ended_at timestamp

**Example:**
```python
session = close_session(session_id="gk_20260223_a3f2c1")
# Returns: {"session_id": "gk_20260223_a3f2c1", "active": false, "ended_at": "..."}
```

### Token Tools

#### submit_token

Submit and validate a completion token.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| token | string | Yes | Token value (GK_COMPLETE_*, TQG_PASS_*, TQG_FAIL_*) |
| session_id | string | Yes | Associated session ID |
| task_id | string | No | Associated task ID |

**Token Formats:**
- `GK_COMPLETE_[32 hex chars]` - Gatekeeper completion
- `TQG_PASS_[32 hex chars]` - Test quality gate pass
- `TQG_FAIL_[32 hex chars]` - Test quality gate failure

**Returns:** Dict with success, token_type, token_value, session_id, task_id, created_at

**Example:**
```python
result = submit_token(
    token="GK_COMPLETE_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    session_id="gk_20260223_a3f2c1",
    task_id="2.1"
)
# Returns: {
#     "success": true,
#     "token_type": "GK_COMPLETE",
#     "token_value": "GK_COMPLETE_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
#     "session_id": "gk_20260223_a3f2c1",
#     "task_id": "2.1",
#     "created_at": "2026-02-23T10:35:00+00:00"
# }
```

#### get_next_task

Get next action after token submission.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| session_id | string | Yes | Session identifier |

**Returns:** Dict with next_action, iteration, has_tokens, max_reached, message

**Example:**
```python
result = get_next_task(session_id="gk_20260223_a3f2c1")
# Returns: {
#     "next_action": "verify",
#     "iteration": 1,
#     "max_iterations": 10,
#     "has_tokens": true,
#     "tokens_count": 1,
#     "has_gk_complete": true,
#     "has_tqg_pass": false,
#     "message": "Verification token submitted, ready for verification check"
# }
```

#### get_token_status

Query token status for a session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| session_id | string | Yes | Session identifier |

**Returns:** Dict with total_count, tokens (list), by_type, latest_token

**Example:**
```python
result = get_token_status(session_id="gk_20260223_a3f2c1")
# Returns: {
#     "session_id": "gk_20260223_a3f2c1",
#     "total_count": 2,
#     "tokens": [...],
#     "by_type": {"GK_COMPLETE": 1, "TQG_PASS": 1},
#     "latest_token": {...}
# }
```

### Signal Tools

#### record_agent_signal

Record an agent signal.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| signal_type | string | Yes | Signal type (see below) |
| session_id | string | No | Associated session ID |
| task_id | string | No | Associated task ID |
| phase_id | integer | No | Associated phase ID |
| agent_id | string | No | Agent identifier |
| context | object | No | Additional context as JSON |

**Signal Types:**
- `TESTS_WRITTEN` - Tests have been written
- `VERIFICATION_PASS` - Verification passed
- `VERIFICATION_FAIL` - Verification failed
- `IMPLEMENTATION_READY` - Implementation is ready
- `ASSESSMENT_PASS` - Assessment passed
- `ASSESSMENT_FAIL` - Assessment failed
- `PHASE_ASSESSMENT_PASS` - Phase-level assessment passed
- `PHASE_VERIFICATION_PASS` - Phase-level verification passed

**Returns:** Dict with success, signal_id, signal_type, pending, created_at

**Example:**
```python
result = record_agent_signal(
    signal_type="TESTS_WRITTEN",
    session_id="gk_20260223_a3f2c1",
    task_id="2.1",
    context={"files": ["test_example.py"]}
)
# Returns: {
#     "success": true,
#     "signal_id": 1,
#     "signal_type": "TESTS_WRITTEN",
#     "pending": true,
#     "created_at": "2026-02-23T10:40:00+00:00"
# }
```

#### get_pending_signals

Query unprocessed signals.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| signal_type | string | No | Filter by signal type |
| session_id | string | No | Filter by session ID |
| task_id | string | No | Filter by task ID |
| phase_id | integer | No | Filter by phase ID |
| limit | integer | No | Maximum results (default: 100) |

**Returns:** Dict with count, signals (list), filters_applied

**Example:**
```python
result = get_pending_signals(
    task_id="2.1",
    signal_type="TESTS_WRITTEN"
)
# Returns: {
#     "signals": [...],
#     "count": 1,
#     "filters_applied": {"task_id": "2.1", "signal_type": "TESTS_WRITTEN"}
# }
```

#### mark_signal_processed

Mark a signal as processed.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| signal_id | integer | Yes | Signal identifier |

**Returns:** Updated signal object with pending=false and processed_at timestamp

**Example:**
```python
result = mark_signal_processed(signal_id=1)
# Returns: {
#     "success": true,
#     "signal_id": 1,
#     "pending": false,
#     "processed_at": "2026-02-23T10:45:00+00:00"
# }
```

### Phase Gate Tools

#### submit_pvg_token

Submit a phase verification gate token.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| session_id | string | Yes | Associated session ID |
| token_value | string | Yes | PVG token (format: PVG_COMPLETE_[32 hex chars]) |
| phase_id | integer | Yes | Phase number |
| integration_check_passed | boolean | Yes | Whether integration check passed |

**Returns:** PhaseToken object

**Example:**
```python
result = submit_pvg_token(
    session_id="gk_20260223_a3f2c1",
    token_value="PVG_COMPLETE_abc123def456...",
    phase_id=6,
    integration_check_passed=True
)
# Returns: {
#     "session_id": "gk_20260223_a3f2c1",
#     "token_value": "PVG_COMPLETE_abc123def456...",
#     "phase_id": 6,
#     "integration_check_passed": true,
#     "created_at": "2026-02-23T11:00:00+00:00"
# }
```

#### check_phase_integration

Verify cross-phase artifact dependencies.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| phase_id | integer | Yes | Current phase number |
| required_artifacts | array | Yes | List of required artifact paths |
| project_dir | string | No | Project directory for path resolution |

**Returns:** Dict with status (PASS/NEEDS_FIXES), details, missing_artifacts, prior_phase_status

**Example:**
```python
result = check_phase_integration(
    phase_id=6,
    required_artifacts=["phase-5.yaml", "task-5.1.md"],
    project_dir="/workspace/craftium"
)
# Returns: {
#     "status": "PASS",
#     "phase_id": 6,
#     "missing_artifacts": [],
#     "details": [
#         {"artifact": "phase-5.yaml", "exists": true},
#         {"artifact": "task-5.1.md", "exists": true}
#     ],
#     "prior_phase_status": {...}
# }
```

### Evolution Tools

#### record_evolution_attempt

Store attempt metrics and outcome.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| task_id | string | Yes | Task identifier |
| attempt_number | integer | Yes | Attempt number (1, 2, 3, ...) |
| outcome | string | Yes | Outcome: SUCCESS, FAILURE, or PARTIAL |
| metrics | object | No | Metrics dict (tests_passed, coverage_percent, errors, etc.) |
| session_id | string | No | Associated session ID |

**Returns:** EvolutionAttempt object

**Example:**
```python
result = record_evolution_attempt(
    task_id="2.1",
    attempt_number=1,
    outcome="FAILURE",
    metrics={"tests_passed": 8, "coverage_percent": 75.5},
    session_id="gk_20260223_a3f2c1"
)
# Returns: {
#     "id": 1,
#     "task_id": "2.1",
#     "attempt_number": 1,
#     "outcome": "FAILURE",
#     "metrics_json": {"tests_passed": 8, "coverage_percent": 75.5},
#     "created_at": "2026-02-23T11:15:00+00:00"
# }
```

#### get_evolution_context

Retrieve historical attempts for a task.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| task_id | string | Yes | Task identifier |
| include_metrics | boolean | No | Include full metrics (default: true) |

**Returns:** Dict with task_id, total_attempts, attempts (list), best_attempt, summary, pattern (IMPROVING/DECLINING/STABLE/UNKNOWN)

**Example:**
```python
result = get_evolution_context(task_id="2.1")
# Returns: {
#     "task_id": "2.1",
#     "total_attempts": 3,
#     "attempts": [...],
#     "summary": {
#         "total_attempts": 3,
#         "success_count": 1,
#         "failure_count": 2,
#         "partial_count": 0
#     },
#     "best_attempt": {...},
#     "pattern": "IMPROVING"
# }
```

## State File Compatibility

The MCP server maintains backward compatibility with `stop-hook.sh` by writing state files:

### verifier-loop.local.md

```markdown
---
session_id: gk_20260223_a3f2c1
iteration: 1
max_iterations: 10
started_at: 2026-02-23T10:30:00+00:00
task_id: "2.1"
project_dir: /workspace/myproject
test_command: pytest tests/ -v
plan_mode: false
---

# Verification Loop State
```

### verifier-token.secret

```
GK_COMPLETE_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
dGVzdCBjb21tYW5kIGJhc2U2NA==
a1b2c3d4e5f6... (SHA-256 hash of test_command)
```

These files are read by the existing `stop-hook.sh` to maintain compatibility with the legacy verification loop while migrating to MCP-based tooling.

## Error Handling

All tools return errors as JSON-RPC errors with descriptive messages:

```json
{
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": "Invalid token format. Expected: GK_COMPLETE_[32 hex chars]"
  }
}
```

Common errors:
- **ValueError**: Invalid parameters (token format, session not found, etc.)
- **RuntimeError**: Database operation failed
- **TypeError**: Wrong parameter type

## Development

### Running Tests

```bash
# Unit tests
pytest tests/python/test_gatekeeper_mcp.py -v

# With coverage
pytest tests/python/ --cov=gatekeeper_mcp --cov-report=term-missing

# Integration tests
bats tests/bash/gatekeeper-mcp.bats
```

### Project Structure

```
gatekeeper-mcp/
  src/gatekeeper_mcp/
    __init__.py
    __main__.py         # Entry point for python -m
    server_v3.py        # FastMCP server entry point
    config.py           # Configuration management
    database.py         # SQLite DatabaseManager
    models.py           # Dataclasses for data types
    validators.py       # Token format validation
    signal_types.py     # Signal type definitions
    state_writer.py     # State file generation
    logging_config.py   # Structured logging setup
    tools/
      __init__.py
      sessions.py       # Session tools
      tokens.py         # Token tools
      signals.py        # Signal tools
      phase_gates.py    # Phase gate tools
      evolution.py      # Evolution tools
    templates/
      __init__.py
      verifier_loop.md.j2   # Jinja2 template for state file
      token_secret.j2       # Jinja2 template for token file
  pyproject.toml       # Package configuration
  README.md            # This file
```

## Migration from File-Based Tokens

The MCP server replaces the previous approach of:
- Writing tokens directly to `.claude/verifier-token.secret`
- Bash scripts parsing state files
- Scattered token validation logic

With MCP:
1. All token operations go through `submit_token` tool
2. Session state is queryable via `get_session` tool
3. Signal-based workflow replaces file polling
4. State files are still written for backward compatibility

## Token Format Specifications

All tokens follow the format: `TYPE_[32 lowercase hex characters]`

- **GK_COMPLETE_[a-f0-9]{32}** - Gatekeeper completion token
- **TQG_PASS_[a-f0-9]{32}** - Test quality gate pass token
- **TQG_FAIL_[a-f0-9]{32}** - Test quality gate fail token
- **PVG_COMPLETE_[a-f0-9]{32}** - Phase verification gate token

The 32-character hex string is typically a random UUID or hash.

## Signal Workflow

1. Agent outputs signal (e.g., `TESTS_WRITTEN`)
2. Agent calls `record_agent_signal()` -> Signal stored with `pending=true`
3. Orchestrator calls `get_pending_signals()` -> Returns unprocessed signals
4. Orchestrator processes signal and calls `mark_signal_processed()`
5. Signal marked with `pending=false` and `processed_at` timestamp
6. If signal is a completion signal, state files are written

## Related Documentation

- **Token Formats** - See `docs/token-formats.md` for detailed token format documentation
- **API Reference** - See docstrings in `src/gatekeeper_mcp/tools/*.py` for complete parameter and return type documentation
- **Architecture** - See system design diagrams above for overview

## License

MIT
