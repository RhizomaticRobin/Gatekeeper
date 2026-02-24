"""
Session lifecycle MCP tools for Gatekeeper server.

Provides tools for:
- create_session: Initialize new verification loop session
- get_session: Retrieve session by ID
- close_session: Mark session as ended
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastmcp import FastMCP
from gatekeeper_mcp.models import Session
from gatekeeper_mcp.database import DatabaseManager

logger = logging.getLogger(__name__)

# Database manager will be injected from server_v3
_db: Optional[DatabaseManager] = None


def register_tools(mcp: FastMCP, db: DatabaseManager) -> None:
    """
    Register session tools with FastMCP server.

    Args:
        mcp: FastMCP server instance
        db: DatabaseManager instance from server
    """
    global _db
    _db = db

    # Register tools
    mcp.tool()(create_session)
    mcp.tool()(get_session)
    mcp.tool()(close_session)

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

    Raises:
        ValueError: If session_id already exists
        RuntimeError: If database operation fails

    Example:
        session = create_session(
            session_id="gk_20260223_a3f2c1",
            project_dir="/workspace/craftium",
            test_command="pytest tests/"
        )
        # Returns: {"session_id": "gk_20260223_a3f2c1", "started_at": "...", ...}
    """
    logger.info("Creating session", extra={
        'tool_name': 'create_session',
        'session_id': session_id,
        'task_id': task_id
    })

    # Check if session already exists
    existing = _db.fetchone('SELECT session_id FROM sessions WHERE session_id = ?', (session_id,))
    if existing:
        logger.error(f"Session already exists: {session_id}", extra={'tool_name': 'create_session'})
        raise ValueError(f"Session with id '{session_id}' already exists")

    # Create session data
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
        # Insert into database
        _db.insert('sessions', session_data)

        # Retrieve created session
        row = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
        session = Session.from_row(row)

        logger.info("Session created successfully", extra={
            'tool_name': 'create_session',
            'session_id': session_id,
            'started_at': started_at
        })

        return session.to_dict()

    except Exception as e:
        logger.error(f"Failed to create session: {e}", extra={
            'tool_name': 'create_session',
            'session_id': session_id
        })
        raise RuntimeError(f"Failed to create session: {e}")


def get_session(session_id: str) -> Dict[str, Any]:
    """
    Retrieve a session by ID.

    Args:
        session_id: Unique session identifier

    Returns:
        Dict containing Session dataclass fields

    Raises:
        ValueError: If session not found

    Example:
        session = get_session("gk_20260223_a3f2c1")
        # Returns: {"session_id": "gk_20260223_a3f2c1", "active": true, ...}
    """
    logger.info("Retrieving session", extra={
        'tool_name': 'get_session',
        'session_id': session_id
    })

    row = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))

    if not row:
        logger.error(f"Session not found: {session_id}", extra={'tool_name': 'get_session'})
        raise ValueError(f"Session with id '{session_id}' not found")

    session = Session.from_row(row)

    logger.info("Session retrieved", extra={
        'tool_name': 'get_session',
        'session_id': session_id,
        'active': session.active
    })

    return session.to_dict()


def close_session(session_id: str) -> Dict[str, Any]:
    """
    Close a session by marking it as ended.

    Args:
        session_id: Unique session identifier

    Returns:
        Dict containing updated Session dataclass fields with ended_at set

    Raises:
        ValueError: If session not found or already closed

    Example:
        session = close_session("gk_20260223_a3f2c1")
        # Returns: {"session_id": "gk_20260223_a3f2c1", "active": false, "ended_at": "...", ...}
    """
    logger.info("Closing session", extra={
        'tool_name': 'close_session',
        'session_id': session_id
    })

    # Check if session exists and is active
    row = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
    if not row:
        logger.error(f"Session not found: {session_id}", extra={'tool_name': 'close_session'})
        raise ValueError(f"Session with id '{session_id}' not found")

    session = Session.from_row(row)
    if not session.active:
        logger.error(f"Session already closed: {session_id}", extra={'tool_name': 'close_session'})
        raise ValueError(f"Session with id '{session_id}' is already closed")

    # Update session
    ended_at = datetime.now(timezone.utc).isoformat()
    rows_updated = _db.update(
        'sessions',
        {'ended_at': ended_at, 'active': 0},
        'session_id = ?',
        (session_id,)
    )

    if rows_updated == 0:
        logger.error(f"Failed to close session: {session_id}", extra={'tool_name': 'close_session'})
        raise RuntimeError(f"Failed to close session '{session_id}'")

    # Retrieve updated session
    row = _db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
    session = Session.from_row(row)

    logger.info("Session closed successfully", extra={
        'tool_name': 'close_session',
        'session_id': session_id,
        'ended_at': ended_at
    })

    return session.to_dict()
