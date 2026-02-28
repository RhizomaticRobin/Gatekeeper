"""
Signal MCP tools for Gatekeeper Evolve server.

Provides tools for:
- record_agent_signal: Record an agent output signal
- get_pending_signals: Query unprocessed signals
- mark_signal_processed: Mark a signal as processed
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, TYPE_CHECKING

from fastmcp import FastMCP
from gatekeeper_evolve_mcp.models import AgentSignal
from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.signal_types import SignalType, validate_signal_type, is_completion_signal
from gatekeeper_evolve_mcp.validators import validate_session_id, ValidationError

if TYPE_CHECKING:
    from gatekeeper_evolve_mcp.state_writer import StateWriter

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None
_state_writer: Optional["StateWriter"] = None


def register_tools(mcp: FastMCP, db: DatabaseManager, state_writer: Optional["StateWriter"] = None) -> None:
    """Register signal tools with FastMCP server."""
    global _db, _state_writer
    _db = db
    _state_writer = state_writer
    mcp.tool()(record_agent_signal)
    mcp.tool()(get_pending_signals)
    mcp.tool()(mark_signal_processed)
    logger.info("Signal tools registered", extra={'tool_name': 'signals'})


def record_agent_signal(
    signal_type: str,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    phase_id: Optional[int] = None,
    agent_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Record an agent output signal.

    Args:
        signal_type: Type of signal (e.g., TESTS_WRITTEN, VERIFICATION_PASS)
        session_id: Optional session ID to link signal to
        task_id: Optional task ID
        phase_id: Optional phase ID
        agent_id: Optional agent identifier
        context: Optional dictionary with additional context

    Returns:
        Dict containing: success, signal_id, signal_type, created_at, pending
    """
    if session_id is not None:
        try:
            validate_session_id(session_id)
        except ValidationError as e:
            raise ValueError(str(e))

    validated_type = validate_signal_type(signal_type)

    created_at = datetime.now(timezone.utc).isoformat()
    signal_data = {
        'session_id': session_id,
        'signal_type': validated_type.value,
        'task_id': task_id,
        'phase_id': phase_id,
        'agent_id': agent_id,
        'context_json': json.dumps(context) if context else None,
        'pending': 1,
        'created_at': created_at,
        'processed_at': None
    }

    signal_id = _db.insert('agent_signals', signal_data)

    return {
        'success': True,
        'signal_id': signal_id,
        'signal_type': validated_type.value,
        'session_id': session_id,
        'task_id': task_id,
        'phase_id': phase_id,
        'created_at': created_at,
        'pending': True
    }


def get_pending_signals(
    session_id: Optional[str] = None,
    signal_type: Optional[str] = None,
    task_id: Optional[str] = None,
    phase_id: Optional[int] = None,
    limit: Optional[int] = 100
) -> Dict[str, Any]:
    """Get pending (unprocessed) signals with optional filters."""
    query = "SELECT * FROM agent_signals WHERE pending = 1"
    params: List[Any] = []

    if session_id is not None:
        query += " AND session_id = ?"
        params.append(session_id)
    if signal_type is not None:
        validated_type = validate_signal_type(signal_type)
        query += " AND signal_type = ?"
        params.append(validated_type.value)
    if task_id is not None:
        query += " AND task_id = ?"
        params.append(task_id)
    if phase_id is not None:
        query += " AND phase_id = ?"
        params.append(phase_id)

    query += " ORDER BY created_at ASC"
    if limit is not None:
        query += f" LIMIT {limit}"

    rows = _db.fetchall(query, tuple(params))
    signals = [AgentSignal.from_row(row).to_dict() for row in rows]

    filters_applied = {
        'session_id': session_id, 'signal_type': signal_type,
        'task_id': task_id, 'phase_id': phase_id, 'limit': limit
    }
    filters_applied = {k: v for k, v in filters_applied.items() if v is not None}

    return {
        'signals': signals,
        'count': len(signals),
        'filters_applied': filters_applied
    }


def mark_signal_processed(signal_id: int) -> Dict[str, Any]:
    """Mark a signal as processed."""
    row = _db.fetchone('SELECT * FROM agent_signals WHERE id = ?', (signal_id,))
    if not row:
        raise ValueError(f"Signal with id {signal_id} not found")

    signal = AgentSignal.from_row(row)
    if not signal.pending:
        raise ValueError(f"Signal with id {signal_id} is already processed")

    processed_at = datetime.now(timezone.utc).isoformat()
    _db.update('agent_signals', {'pending': 0, 'processed_at': processed_at}, 'id = ?', (signal_id,))

    row = _db.fetchone('SELECT * FROM agent_signals WHERE id = ?', (signal_id,))
    updated_signal = AgentSignal.from_row(row)

    if _state_writer and is_completion_signal(SignalType(updated_signal.signal_type)):
        try:
            token = None
            if updated_signal.session_id:
                token_row = _db.fetchone(
                    'SELECT token_value FROM completion_tokens WHERE session_id = ? ORDER BY created_at DESC LIMIT 1',
                    (updated_signal.session_id,)
                )
                if token_row:
                    token = token_row['token_value']
            _state_writer.write_state_files(updated_signal.session_id, token=token)
        except Exception as e:
            logger.error(f"Failed to write state files: {e}", extra={'tool_name': 'mark_signal_processed'})

    result = updated_signal.to_dict()
    result['success'] = True
    return result
