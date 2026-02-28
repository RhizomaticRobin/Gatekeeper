"""
Token submission MCP tools for Gatekeeper Evolve server.

Provides tools for:
- submit_token: Submit completion/test quality gate tokens
- get_next_task: Get next task information based on session state
- get_token_status: Get token submission status for a session
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, TYPE_CHECKING

from fastmcp import FastMCP
from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.validators import validate_token_format, validate_session_id, ValidationError

if TYPE_CHECKING:
    from gatekeeper_evolve_mcp.state_writer import StateWriter

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None
_state_writer: Optional["StateWriter"] = None


def register_tools(mcp: FastMCP, db: DatabaseManager, state_writer: Optional["StateWriter"] = None) -> None:
    """Register token tools with FastMCP server."""
    global _db, _state_writer
    _db = db
    _state_writer = state_writer
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

    Args:
        token: Token string (format: GK_COMPLETE_[32hex] or TQG_PASS_[32hex])
        session_id: Session identifier (format: gk_YYYYMMDD_[6hex])
        task_id: Optional task ID associated with this token

    Returns:
        Dict containing success status and token details
    """
    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    try:
        token_type = validate_token_format(token)
    except ValidationError as e:
        raise ValueError(str(e))

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
        with _db.transaction() as conn:
            session_row = _db.execute(
                conn, 'SELECT session_id, active FROM sessions WHERE session_id = ?', (session_id,)
            ).fetchone()
            if not session_row:
                raise ValueError(f"Session with id '{session_id}' not found")
            if not session_row['active']:
                raise ValueError(f"Session with id '{session_id}' is not active")

            existing_token = _db.execute(
                conn, 'SELECT token_value FROM completion_tokens WHERE token_value = ?', (token,)
            ).fetchone()
            if existing_token:
                raise ValueError(f"Token '{token[:20]}...' already exists")

            columns = ', '.join(token_data.keys())
            placeholders = ', '.join(['?' for _ in token_data])
            _db.execute(conn, f'INSERT INTO completion_tokens ({columns}) VALUES ({placeholders})', tuple(token_data.values()))

    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to submit token: {e}")

    # Advisory check: warn if verification_level is set but no passing verification results exist
    try:
        session_row_full = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
        if session_row_full:
            # Check if verification_results table exists and has passing results
            vr_table = _db.fetchone(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_results'"
            )
            if vr_table:
                passing_vr = _db.fetchone(
                    "SELECT id FROM verification_results WHERE session_id = ? AND status = 'pass'",
                    (session_id,)
                )
                if not passing_vr:
                    logger.warning(
                        f"Token submitted for session {session_id} but no passing verification_results found. "
                        "If formal verification is expected, run run_verification() before submitting tokens.",
                        extra={'tool_name': 'submit_token', 'session_id': session_id, 'task_id': task_id}
                    )
    except Exception as e:
        # Advisory only — never block token submission
        logger.debug(f"Advisory verification check failed (non-blocking): {e}", extra={'tool_name': 'submit_token'})

    if _state_writer:
        try:
            _state_writer.write_state_files(session_id, token=token)
        except Exception as e:
            logger.error(f"Failed to write state files: {e}", extra={'tool_name': 'submit_token'})

    return {
        'success': True,
        'token_type': token_type,
        'token_value': token,
        'session_id': session_id,
        'task_id': task_id,
        'created_at': created_at
    }


def get_next_task(session_id: str) -> Dict[str, Any]:
    """Get next task information based on session state and token history."""
    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    session_row = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
    if not session_row:
        raise ValueError(f"Session '{session_id}' not found")

    token_rows = _db.fetchall('SELECT * FROM completion_tokens WHERE session_id = ?', (session_id,))

    iteration = session_row['iteration']
    max_iterations = session_row['max_iterations']
    active = bool(session_row['active'])
    tokens_count = len(token_rows)
    has_tokens = tokens_count > 0
    has_gk_complete = any(row['token_type'] == 'GK_COMPLETE' for row in token_rows)
    has_tqg_pass = any(row['token_type'] == 'TQG_PASS' for row in token_rows)

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

    return {
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


def get_token_status(session_id: str) -> Dict[str, Any]:
    """Get token submission status and history for a session."""
    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    session_row = _db.fetchone('SELECT session_id FROM sessions WHERE session_id = ?', (session_id,))
    if not session_row:
        raise ValueError(f"Session '{session_id}' not found")

    token_rows = _db.fetchall(
        '''SELECT token_type, token_value, created_at, validated, task_id
           FROM completion_tokens
           WHERE session_id = ?
           ORDER BY created_at DESC''',
        (session_id,)
    )

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
        if row['token_type'] in by_type:
            by_type[row['token_type']] += 1
        if latest_token is None:
            latest_token = token_dict

    return {
        'session_id': session_id,
        'tokens': tokens,
        'total_count': len(tokens),
        'by_type': by_type,
        'latest_token': latest_token
    }
