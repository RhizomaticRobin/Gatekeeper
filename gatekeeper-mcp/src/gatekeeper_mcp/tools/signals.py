"""
Signal MCP tools for Gatekeeper server.

Provides tools for:
- record_agent_signal: Record an agent output signal
- get_pending_signals: Query unprocessed signals
- mark_signal_processed: Mark a signal as processed

Signal Workflow:
1. Agent outputs signal (e.g., TESTS_WRITTEN)
2. Agent calls record_agent_signal() -> Signal stored with pending=true
3. Orchestrator calls get_pending_signals() -> Returns unprocessed signals
4. Orchestrator processes signal and calls mark_signal_processed()
5. Signal marked with pending=false and processed_at timestamp
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, TYPE_CHECKING

from fastmcp import FastMCP
from gatekeeper_mcp.models import AgentSignal
from gatekeeper_mcp.database import DatabaseManager
from gatekeeper_mcp.signal_types import SignalType, validate_signal_type, is_completion_signal

if TYPE_CHECKING:
    from gatekeeper_mcp.state_writer import StateWriter

logger = logging.getLogger(__name__)

# Database manager and state writer will be injected from server_v3
_db: Optional[DatabaseManager] = None
_state_writer: Optional["StateWriter"] = None


def register_tools(mcp: FastMCP, db: DatabaseManager, state_writer: Optional["StateWriter"] = None) -> None:
    """
    Register signal tools with FastMCP server.

    Args:
        mcp: FastMCP server instance
        db: DatabaseManager instance from server
        state_writer: StateWriter instance from server (optional)
    """
    global _db, _state_writer
    _db = db
    _state_writer = state_writer

    # Register tools
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

    Agents call this tool to emit signals that communicate their progress
    to the orchestrator. Signals are stored with pending=true for the
    orchestrator to process.

    Args:
        signal_type: Type of signal (e.g., TESTS_WRITTEN, VERIFICATION_PASS)
        session_id: Optional session ID to link signal to a verification loop
        task_id: Optional task ID for plan mode
        phase_id: Optional phase ID for phase-level signals
        agent_id: Optional agent identifier
        context: Optional dictionary with additional context

    Returns:
        Dict containing: success, signal_id, signal_type, created_at, pending

    Raises:
        ValueError: If signal_type is invalid

    Example:
        result = record_agent_signal(
            signal_type="TESTS_WRITTEN",
            task_id="1.1",
            context={"files": ["test_example.py"]}
        )
        # Returns: {"success": true, "signal_id": 1, "signal_type": "TESTS_WRITTEN", ...}
    """
    logger.info("Recording agent signal", extra={
        'tool_name': 'record_agent_signal',
        'signal_type': signal_type,
        'session_id': session_id,
        'task_id': task_id
    })

    # Validate signal type
    try:
        validated_type = validate_signal_type(signal_type)
    except ValueError as e:
        logger.error(f"Invalid signal type: {signal_type}", extra={
            'tool_name': 'record_agent_signal'
        })
        raise

    # Create signal data
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

    try:
        # Insert into database
        signal_id = _db.insert('agent_signals', signal_data)

        logger.info("Signal recorded successfully", extra={
            'tool_name': 'record_agent_signal',
            'signal_id': signal_id,
            'signal_type': validated_type.value,
            'pending': True
        })

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

    except Exception as e:
        logger.error(f"Failed to record signal: {e}", extra={
            'tool_name': 'record_agent_signal',
            'signal_type': signal_type
        })
        raise RuntimeError(f"Failed to record signal: {e}")


def get_pending_signals(
    session_id: Optional[str] = None,
    signal_type: Optional[str] = None,
    task_id: Optional[str] = None,
    phase_id: Optional[int] = None,
    limit: Optional[int] = 100
) -> Dict[str, Any]:
    """
    Get pending (unprocessed) signals.

    The orchestrator calls this tool to query signals that have not been
    processed. Signals are NOT automatically marked as processed - the
    orchestrator must explicitly call mark_signal_processed().

    Args:
        session_id: Optional filter by session ID
        signal_type: Optional filter by signal type
        task_id: Optional filter by task ID
        phase_id: Optional filter by phase ID
        limit: Maximum number of signals to return (default: 100)

    Returns:
        Dict containing:
        - signals: List of signal dictionaries
        - count: Number of signals returned
        - filters_applied: Dict of filters that were applied

    Example:
        result = get_pending_signals(task_id="1.1", signal_type="TESTS_WRITTEN")
        # Returns: {"signals": [...], "count": 1, "filters_applied": {...}}
    """
    logger.info("Querying pending signals", extra={
        'tool_name': 'get_pending_signals',
        'session_id': session_id,
        'signal_type': signal_type,
        'task_id': task_id
    })

    # Build query with filters
    query = "SELECT * FROM agent_signals WHERE pending = 1"
    params: List[Any] = []

    if session_id is not None:
        query += " AND session_id = ?"
        params.append(session_id)

    if signal_type is not None:
        # Validate signal type for consistent querying
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

    # Execute query
    rows = _db.fetchall(query, tuple(params))

    # Convert to AgentSignal dataclass instances
    signals = []
    for row in rows:
        signal = AgentSignal.from_row(row)
        signals.append(signal.to_dict())

    filters_applied = {
        'session_id': session_id,
        'signal_type': signal_type,
        'task_id': task_id,
        'phase_id': phase_id,
        'limit': limit
    }
    # Remove None values from filters_applied
    filters_applied = {k: v for k, v in filters_applied.items() if v is not None}

    logger.info("Pending signals retrieved", extra={
        'tool_name': 'get_pending_signals',
        'count': len(signals)
    })

    return {
        'signals': signals,
        'count': len(signals),
        'filters_applied': filters_applied
    }


def mark_signal_processed(
    signal_id: int
) -> Dict[str, Any]:
    """
    Mark a signal as processed.

    The orchestrator calls this tool after processing a signal to mark it
    as complete. This sets pending=false and records the processed_at timestamp.

    If the signal indicates a session state change (e.g., VERIFICATION_PASS),
    this may trigger a state file write (Phase 7).

    Args:
        signal_id: ID of the signal to mark as processed

    Returns:
        Dict containing updated signal details

    Raises:
        ValueError: If signal not found or already processed

    Example:
        result = mark_signal_processed(signal_id=1)
        # Returns: {"success": true, "signal_id": 1, "pending": false, "processed_at": "..."}
    """
    logger.info("Marking signal as processed", extra={
        'tool_name': 'mark_signal_processed',
        'signal_id': signal_id
    })

    # Check if signal exists and is pending
    row = _db.fetchone(
        'SELECT * FROM agent_signals WHERE id = ?',
        (signal_id,)
    )

    if not row:
        logger.error(f"Signal not found: {signal_id}", extra={
            'tool_name': 'mark_signal_processed'
        })
        raise ValueError(f"Signal with id {signal_id} not found")

    signal = AgentSignal.from_row(row)

    if not signal.pending:
        logger.error(f"Signal already processed: {signal_id}", extra={
            'tool_name': 'mark_signal_processed'
        })
        raise ValueError(f"Signal with id {signal_id} is already processed")

    # Update signal
    processed_at = datetime.now(timezone.utc).isoformat()
    rows_updated = _db.update(
        'agent_signals',
        {'pending': 0, 'processed_at': processed_at},
        'id = ?',
        (signal_id,)
    )

    if rows_updated == 0:
        logger.error(f"Failed to update signal: {signal_id}", extra={
            'tool_name': 'mark_signal_processed'
        })
        raise RuntimeError(f"Failed to mark signal {signal_id} as processed")

    # Retrieve updated signal
    row = _db.fetchone(
        'SELECT * FROM agent_signals WHERE id = ?',
        (signal_id,)
    )
    updated_signal = AgentSignal.from_row(row)

    # Write state files if this is a completion signal
    if _state_writer and is_completion_signal(SignalType(updated_signal.signal_type)):
        try:
            # Get token for session if available
            token = None
            if updated_signal.session_id:
                token_row = _db.fetchone(
                    'SELECT token_value FROM completion_tokens WHERE session_id = ? ORDER BY created_at DESC LIMIT 1',
                    (updated_signal.session_id,)
                )
                if token_row:
                    token = token_row['token_value']

            _state_writer.write_state_files(updated_signal.session_id, token=token)
            logger.debug(
                "State files written after signal processing",
                extra={'tool_name': 'mark_signal_processed', 'signal_id': signal_id}
            )
        except Exception as e:
            logger.error(
                f"Failed to write state files: {e}",
                extra={'tool_name': 'mark_signal_processed', 'signal_id': signal_id}
            )

    logger.info("Signal marked as processed", extra={
        'tool_name': 'mark_signal_processed',
        'signal_id': signal_id,
        'processed_at': processed_at
    })

    result = updated_signal.to_dict()
    result['success'] = True
    return result
