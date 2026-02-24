"""
Token submission MCP tools for Gatekeeper server.

Provides tools for:
- submit_token: Submit completion/test quality gate tokens
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, TYPE_CHECKING

from fastmcp import FastMCP
from gatekeeper_mcp.database import DatabaseManager
from gatekeeper_mcp.validators import validate_token_format, ValidationError

if TYPE_CHECKING:
    from gatekeeper_mcp.state_writer import StateWriter

logger = logging.getLogger(__name__)

# Database manager and state writer will be injected from server_v3
_db: Optional[DatabaseManager] = None
_state_writer: Optional["StateWriter"] = None


def register_tools(mcp: FastMCP, db: DatabaseManager, state_writer: Optional["StateWriter"] = None) -> None:
    """
    Register token tools with FastMCP server.

    Args:
        mcp: FastMCP server instance
        db: DatabaseManager instance from server
        state_writer: StateWriter instance from server (optional)
    """
    global _db, _state_writer
    _db = db
    _state_writer = state_writer

    # Register tools
    mcp.tool()(submit_token)
    mcp.tool()(get_next_task)
    mcp.tool()(get_token_status)

    logger.info("Token tools registered", extra={'tool_name': 'tokens'})


def submit_token(
    token: str,
    session_id: str,
    task_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit a completion or test quality gate token.

    This MCP tool:
    1. Validates token format using validate_token_format()
    2. Verifies session exists and is active
    3. Inserts token into completion_tokens table
    4. Triggers state file write (placeholder)
    5. Returns success dict with token details

    Args:
        token: Token string (format: GK_COMPLETE_[32hex] or TQG_PASS_[32hex])
        session_id: Session identifier (format: gk_YYYYMMDD_[6hex])
        task_id: Optional task ID associated with this token

    Returns:
        Dict containing:
            - success: True if token submitted successfully
            - token_type: "GK_COMPLETE" or "TQG_PASS"
            - token_value: The submitted token
            - session_id: The session ID
            - task_id: The task ID (or None)
            - created_at: ISO 8601 timestamp

    Raises:
        ValueError: If token format is invalid
        ValueError: If session not found or not active
        ValueError: If token already exists (duplicate)

    Example:
        result = submit_token(
            token="GK_COMPLETE_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
            session_id="gk_20260223_a3f2c1",
            task_id="4.2"
        )
        # Returns: {"success": True, "token_type": "GK_COMPLETE", ...}
    """
    logger.info("Submitting token", extra={
        'tool_name': 'submit_token',
        'session_id': session_id,
        'token_type': None  # Will be set after validation
    })

    # Validate token format and extract token type
    try:
        token_type = validate_token_format(token)
    except ValidationError as e:
        logger.error(f"Token validation failed: {e}", extra={
            'tool_name': 'submit_token',
            'session_id': session_id
        })
        raise ValueError(str(e))

    logger.info("Token format validated", extra={
        'tool_name': 'submit_token',
        'session_id': session_id,
        'token_type': token_type
    })

    # Check if session exists
    session_row = _db.fetchone(
        'SELECT session_id, active FROM sessions WHERE session_id = ?',
        (session_id,)
    )

    if not session_row:
        logger.error(f"Session not found: {session_id}", extra={
            'tool_name': 'submit_token',
            'session_id': session_id,
            'token_type': token_type
        })
        raise ValueError(f"Session with id '{session_id}' not found")

    # Check if session is active
    if not session_row['active']:
        logger.error(f"Session not active: {session_id}", extra={
            'tool_name': 'submit_token',
            'session_id': session_id,
            'token_type': token_type
        })
        raise ValueError(f"Session with id '{session_id}' is not active")

    # Check for duplicate token
    existing_token = _db.fetchone(
        'SELECT token_value FROM completion_tokens WHERE token_value = ?',
        (token,)
    )

    if existing_token:
        logger.error(f"Token already exists: {token[:20]}...", extra={
            'tool_name': 'submit_token',
            'session_id': session_id,
            'token_type': token_type
        })
        raise ValueError(f"Token '{token[:20]}...' already exists")

    # Insert token into database
    created_at = datetime.now(timezone.utc).isoformat()

    token_data = {
        'session_id': session_id,
        'token_type': token_type,
        'token_value': token,
        'task_id': task_id,
        'created_at': created_at,
        'validated': 0
    }

    try:
        _db.insert('completion_tokens', token_data)

        logger.info("Token inserted successfully", extra={
            'tool_name': 'submit_token',
            'session_id': session_id,
            'token_type': token_type,
            'created_at': created_at
        })

    except Exception as e:
        logger.error(f"Failed to insert token: {e}", extra={
            'tool_name': 'submit_token',
            'session_id': session_id,
            'token_type': token_type
        })
        raise RuntimeError(f"Failed to submit token: {e}")

    # Write state files (actual implementation replacing placeholder)
    if _state_writer:
        try:
            _state_writer.write_state_files(session_id, token=token)
            logger.debug(
                "State files written after token submission",
                extra={'tool_name': 'submit_token', 'session_id': session_id}
            )
        except Exception as e:
            # Log error but don't fail the operation
            logger.error(
                f"Failed to write state files: {e}",
                extra={'tool_name': 'submit_token', 'session_id': session_id}
            )

    # Return success response
    return {
        'success': True,
        'token_type': token_type,
        'token_value': token,
        'session_id': session_id,
        'task_id': task_id,
        'created_at': created_at
    }


def get_next_task(session_id: str) -> Dict[str, Any]:
    """
    Get next task information based on session state and token history.

    Analyzes session iteration count, max_iterations, and submitted tokens
    to determine the next action for the orchestrator.

    Args:
        session_id: Session identifier to query

    Returns:
        Dict containing:
            - next_action: str - "continue", "verify", "complete", or "max_reached"
            - iteration: int - Current iteration number
            - max_iterations: int - Maximum allowed iterations
            - has_tokens: bool - Whether session has any tokens
            - tokens_count: int - Total number of tokens
            - has_gk_complete: bool - Whether session has GK_COMPLETE token
            - has_tqg_pass: bool - Whether session has TQG_PASS token
            - message: str - Human-readable status message
            - session_id: str - Session identifier

    Raises:
        ValueError: If session not found

    Example:
        >>> result = get_next_task("gk_20260223_a3f2c1")
        >>> result['next_action']
        'continue'
        >>> result['iteration']
        1
    """
    logger.info(
        "Getting next task info",
        extra={'tool_name': 'get_next_task', 'session_id': session_id}
    )

    # Get session state
    session_row = _db.fetchone(
        'SELECT * FROM sessions WHERE session_id = ?',
        (session_id,)
    )
    if not session_row:
        logger.error(
            f"Session not found: {session_id}",
            extra={'tool_name': 'get_next_task', 'session_id': session_id}
        )
        raise ValueError(f"Session '{session_id}' not found")

    # Get token history
    token_rows = _db.fetchall(
        'SELECT * FROM completion_tokens WHERE session_id = ?',
        (session_id,)
    )

    # Parse session data
    iteration = session_row['iteration']
    max_iterations = session_row['max_iterations']
    active = bool(session_row['active'])

    # Parse token data
    tokens_count = len(token_rows)
    has_tokens = tokens_count > 0

    # Check for specific token types
    has_gk_complete = any(
        row['token_type'] == 'GK_COMPLETE' for row in token_rows
    )
    has_tqg_pass = any(
        row['token_type'] == 'TQG_PASS' for row in token_rows
    )

    # Determine next action
    if not active:
        next_action = "complete"
        message = "Session is closed"
    elif has_gk_complete:
        next_action = "verify"
        message = "Verification token submitted, ready for verification check"
    elif iteration >= max_iterations:
        next_action = "max_reached"
        message = f"Maximum iterations ({max_iterations}) reached without completion token"
    else:
        next_action = "continue"
        message = f"Iteration {iteration} of {max_iterations}, awaiting token submission"

    result = {
        'next_action': next_action,
        'iteration': iteration,
        'max_iterations': max_iterations,
        'has_tokens': has_tokens,
        'tokens_count': tokens_count,
        'has_gk_complete': has_gk_complete,
        'has_tqg_pass': has_tqg_pass,
        'message': message,
        'session_id': session_id
    }

    logger.info(
        f"Next task determined: {next_action}",
        extra={
            'tool_name': 'get_next_task',
            'session_id': session_id,
            'next_action': next_action,
            'iteration': iteration,
            'tokens_count': tokens_count
        }
    )

    return result


def get_token_status(session_id: str) -> Dict[str, Any]:
    """
    Get token submission status and history for a session.

    Lists all tokens submitted for the session with details and
    provides summary statistics by token type.

    Args:
        session_id: Session identifier to query

    Returns:
        Dict containing:
            - session_id: str - Session identifier
            - tokens: list - List of token dicts with type, value, created_at
            - total_count: int - Total number of tokens
            - by_type: dict - Counts by token type {"GK_COMPLETE": n, "TQG_PASS": m}
            - latest_token: Optional[dict] - Most recently submitted token

    Raises:
        ValueError: If session not found

    Example:
        >>> result = get_token_status("gk_20260223_a3f2c1")
        >>> result['total_count']
        2
        >>> result['by_type']
        {'GK_COMPLETE': 1, 'TQG_PASS': 1}
    """
    logger.info(
        "Getting token status",
        extra={'tool_name': 'get_token_status', 'session_id': session_id}
    )

    # Verify session exists
    session_row = _db.fetchone(
        'SELECT session_id FROM sessions WHERE session_id = ?',
        (session_id,)
    )
    if not session_row:
        logger.error(
            f"Session not found: {session_id}",
            extra={'tool_name': 'get_token_status', 'session_id': session_id}
        )
        raise ValueError(f"Session '{session_id}' not found")

    # Get all tokens for session
    token_rows = _db.fetchall(
        '''SELECT token_type, token_value, created_at, validated, task_id
           FROM completion_tokens
           WHERE session_id = ?
           ORDER BY created_at DESC''',
        (session_id,)
    )

    # Build token list
    tokens = []
    by_type = {'GK_COMPLETE': 0, 'TQG_PASS': 0}
    latest_token = None

    for row in token_rows:
        token_dict = {
            'token_type': row['token_type'],
            'token_value': row['token_value'],
            'created_at': row['created_at'],
            'validated': bool(row['validated']),
            'task_id': row['task_id'],
            'session_id': session_id
        }
        tokens.append(token_dict)

        # Count by type
        if row['token_type'] in by_type:
            by_type[row['token_type']] += 1

        # Track latest (first in DESC order)
        if latest_token is None:
            latest_token = token_dict

    result = {
        'session_id': session_id,
        'tokens': tokens,
        'total_count': len(tokens),
        'by_type': by_type,
        'latest_token': latest_token
    }

    logger.info(
        f"Token status retrieved: {len(tokens)} tokens",
        extra={
            'tool_name': 'get_token_status',
            'session_id': session_id,
            'total_count': len(tokens),
            'by_type': by_type
        }
    )

    return result
