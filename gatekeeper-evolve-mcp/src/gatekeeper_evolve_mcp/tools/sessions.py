"""
Session lifecycle MCP tools for Gatekeeper Evolve server.

Provides tools for:
- create_session: Initialize new verification loop session
- get_session: Retrieve session by ID
- close_session: Mark session as ended
- purge_closed_sessions: Delete all closed sessions
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastmcp import FastMCP
from gatekeeper_evolve_mcp.models import Session
from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.validators import validate_session_id, ValidationError

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None


def register_tools(mcp: FastMCP, db: DatabaseManager) -> None:
    """Register session tools with FastMCP server."""
    global _db
    _db = db
    mcp.tool()(create_session)
    mcp.tool()(get_session)
    mcp.tool()(close_session)
    mcp.tool()(purge_closed_sessions)
    logger.info("Session tools registered", extra={'tool_name': 'sessions'})


def create_session(
    session_id: str,
    project_dir: str,
    test_command: str,
    verifier_model: str = "sonnet",
    max_iterations: int = 10,
    task_id: Optional[str] = None,
    plan_mode: bool = False
) -> Dict[str, Any]:
    """
    Create a new verification loop session.

    Args:
        session_id: Unique session identifier (format: gk_TIMESTAMP_RANDOMHEX)
        project_dir: Project directory path
        test_command: Test command to run
        verifier_model: Model for verification (default: "sonnet")
        max_iterations: Maximum verification iterations (default: 10)
        task_id: Optional task ID for plan mode
        plan_mode: Whether this is a plan mode session (default: False)

    Returns:
        Dict containing Session dataclass fields
    """
    logger.info("Creating session", extra={
        'tool_name': 'create_session',
        'session_id': session_id,
        'task_id': task_id
    })

    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    started_at = datetime.now(timezone.utc).isoformat()
    session_data = {
        'session_id': session_id,
        'task_id': task_id,
        'iteration': 1,
        'max_iterations': max_iterations,
        'project_dir': project_dir,
        'test_command': test_command,
        'verifier_model': verifier_model,
        'started_at': started_at,
        'ended_at': None,
        'plan_mode': 1 if plan_mode else 0,
        'active': 1
    }

    try:
        with _db.transaction() as conn:
            existing = _db.execute(conn, 'SELECT session_id FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
            if existing:
                raise ValueError(f"Session with id '{session_id}' already exists")
            columns = ', '.join(session_data.keys())
            placeholders = ', '.join(['?' for _ in session_data])
            _db.execute(conn, f'INSERT INTO sessions ({columns}) VALUES ({placeholders})', tuple(session_data.values()))

        row = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
        session = Session.from_row(row)
        return session.to_dict()

    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to create session: {e}")


def get_session(session_id: str) -> Dict[str, Any]:
    """Retrieve a session by ID."""
    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    row = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
    if not row:
        raise ValueError(f"Session with id '{session_id}' not found")

    return Session.from_row(row).to_dict()


def close_session(session_id: str) -> Dict[str, Any]:
    """Close a session by marking it as ended."""
    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    row = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
    if not row:
        raise ValueError(f"Session with id '{session_id}' not found")

    session = Session.from_row(row)
    if not session.active:
        raise ValueError(f"Session with id '{session_id}' is already closed")

    ended_at = datetime.now(timezone.utc).isoformat()
    _db.update('sessions', {'ended_at': ended_at, 'active': 0}, 'session_id = ?', (session_id,))

    row = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
    return Session.from_row(row).to_dict()


def purge_closed_sessions() -> Dict[str, Any]:
    """Delete all closed sessions and their associated data."""
    closed_count_row = _db.fetchone('SELECT COUNT(*) as cnt FROM sessions WHERE active = 0')
    closed_count = closed_count_row['cnt'] if closed_count_row else 0

    if closed_count == 0:
        active_row = _db.fetchone('SELECT COUNT(*) as cnt FROM sessions WHERE active = 1')
        return {
            'purged_count': 0,
            'remaining_active': active_row['cnt'] if active_row else 0
        }

    purged = _db.delete('sessions', 'active = 0')
    active_row = _db.fetchone('SELECT COUNT(*) as cnt FROM sessions WHERE active = 1')
    remaining = active_row['cnt'] if active_row else 0

    return {
        'purged_count': purged,
        'remaining_active': remaining
    }
