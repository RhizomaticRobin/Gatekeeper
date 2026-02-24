"""
Evolution tracking MCP tools for Gatekeeper server.

Provides tools for:
- record_evolution_attempt: Track evolution/retry attempts for a task
- get_evolution_context: Retrieve historical attempts and pattern analysis
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, TYPE_CHECKING

from fastmcp import FastMCP
from gatekeeper_mcp.models import EvolutionAttempt
from gatekeeper_mcp.database import DatabaseManager

if TYPE_CHECKING:
    from gatekeeper_mcp.state_writer import StateWriter

logger = logging.getLogger(__name__)

# Database manager and state writer will be injected from server_v3
_db: Optional[DatabaseManager] = None
_state_writer: Optional["StateWriter"] = None

# Valid outcomes for evolution attempts
VALID_OUTCOMES = {'SUCCESS', 'FAILURE', 'PARTIAL'}


def register_tools(mcp: FastMCP, db: DatabaseManager, state_writer: Optional["StateWriter"] = None) -> None:
    """
    Register evolution tools with FastMCP server.

    Args:
        mcp: FastMCP server instance
        db: DatabaseManager instance from server
        state_writer: StateWriter instance from server (optional)
    """
    global _db, _state_writer
    _db = db
    _state_writer = state_writer

    # Register tools
    mcp.tool()(record_evolution_attempt)
    mcp.tool()(get_evolution_context)

    logger.info("Evolution tools registered", extra={'tool_name': 'evolution'})


def record_evolution_attempt(
    task_id: str,
    attempt_number: int,
    outcome: str,
    metrics: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Record an evolution/retry attempt for a task.

    Args:
        task_id: Task identifier (e.g., "2.1", "3.5")
        attempt_number: Sequential attempt number (1, 2, 3, ...)
        outcome: Outcome of the attempt ('SUCCESS', 'FAILURE', 'PARTIAL')
        metrics: Optional dict with test metrics (tests_passed, coverage, etc.)
        session_id: Optional session ID to link attempt to a verification session

    Returns:
        Dict containing EvolutionAttempt dataclass fields

    Raises:
        ValueError: If outcome is invalid or (task_id, attempt_number) already exists
        RuntimeError: If database operation fails

    Example:
        attempt = record_evolution_attempt(
            task_id="2.1",
            attempt_number=1,
            outcome="FAILURE",
            metrics={"tests_passed": 8, "coverage_percent": 75.5}
        )
        # Returns: {"id": 1, "task_id": "2.1", "attempt_number": 1, ...}
    """
    logger.info("Recording evolution attempt", extra={
        'tool_name': 'record_evolution_attempt',
        'task_id': task_id,
        'attempt_number': attempt_number,
        'outcome': outcome
    })

    # Normalize outcome to uppercase
    outcome_upper = outcome.upper()

    # Validate outcome
    if outcome_upper not in VALID_OUTCOMES:
        logger.error(f"Invalid outcome: {outcome}", extra={'tool_name': 'record_evolution_attempt'})
        raise ValueError(f"Invalid outcome '{outcome}'. Must be one of {VALID_OUTCOMES}")

    # Validate session_id if provided (check if session exists)
    if session_id is not None:
        session_exists = _db.fetchone(
            'SELECT session_id FROM sessions WHERE session_id = ?',
            (session_id,)
        )
        if not session_exists:
            logger.error(
                f"Session {session_id} does not exist",
                extra={'tool_name': 'record_evolution_attempt'}
            )
            raise ValueError(f"Session '{session_id}' does not exist. Session must be created before recording evolution attempts.")

    # Check if attempt already exists
    existing = _db.fetchone(
        'SELECT id FROM evolution_attempts WHERE task_id = ? AND attempt_number = ?',
        (task_id, attempt_number)
    )
    if existing:
        logger.error(
            f"Evolution attempt already exists for task_id={task_id}, attempt_number={attempt_number}",
            extra={'tool_name': 'record_evolution_attempt'}
        )
        raise ValueError(
            f"Evolution attempt with task_id '{task_id}' and attempt_number {attempt_number} already exists"
        )

    # Serialize metrics to JSON
    metrics_json_str = None
    if metrics is not None:
        metrics_json_str = json.dumps(metrics)

    # Create attempt data
    created_at = datetime.now(timezone.utc).isoformat()
    attempt_data = {
        'session_id': session_id,
        'task_id': task_id,
        'attempt_number': attempt_number,
        'metrics_json': metrics_json_str,
        'outcome': outcome_upper,
        'created_at': created_at
    }

    try:
        # Insert into database
        row_id = _db.insert('evolution_attempts', attempt_data)

        # Retrieve created attempt
        row = _db.fetchone(
            'SELECT * FROM evolution_attempts WHERE id = ?',
            (row_id,)
        )
        attempt = EvolutionAttempt.from_row(row)

        # Write state files if session_id provided
        if _state_writer and session_id:
            try:
                _state_writer.write_state_files(session_id)
                logger.debug(
                    "State files written after evolution attempt",
                    extra={'tool_name': 'record_evolution_attempt', 'session_id': session_id}
                )
            except Exception as e:
                logger.error(
                    f"Failed to write state files: {e}",
                    extra={'tool_name': 'record_evolution_attempt', 'session_id': session_id}
                )

        logger.info("Evolution attempt recorded successfully", extra={
            'tool_name': 'record_evolution_attempt',
            'task_id': task_id,
            'attempt_number': attempt_number,
            'outcome': outcome_upper,
            'created_at': created_at
        })

        return attempt.to_dict()

    except Exception as e:
        logger.error(f"Failed to record evolution attempt: {e}", extra={
            'tool_name': 'record_evolution_attempt',
            'task_id': task_id,
            'attempt_number': attempt_number
        })
        raise RuntimeError(f"Failed to record evolution attempt: {e}")


def get_evolution_context(
    task_id: str,
    include_metrics: bool = True
) -> Dict[str, Any]:
    """
    Get evolution context for a task, including all historical attempts.

    Args:
        task_id: Task identifier (e.g., "2.1", "3.5")
        include_metrics: Whether to include metrics in the response (default: True)

    Returns:
        Dict containing:
        - task_id: Task identifier
        - total_attempts: Total number of attempts
        - attempts: List of attempt dicts sorted by attempt_number
        - summary: Counts of SUCCESS/FAILURE/PARTIAL outcomes
        - best_attempt: Attempt with best metrics (if available)
        - pattern: IMPROVING/DECLINING/STABLE/UNKNOWN
        - retrieved_at: ISO 8601 timestamp

    Example:
        context = get_evolution_context("2.1")
        # Returns: {
        #     "task_id": "2.1",
        #     "total_attempts": 3,
        #     "attempts": [...],
        #     "summary": {"total_attempts": 3, "success_count": 1, ...},
        #     "best_attempt": {...},
        #     "pattern": "IMPROVING"
        # }
    """
    logger.info("Getting evolution context", extra={
        'tool_name': 'get_evolution_context',
        'task_id': task_id
    })

    # Query all attempts for task_id, sorted by attempt_number
    rows = _db.fetchall(
        'SELECT * FROM evolution_attempts WHERE task_id = ? ORDER BY attempt_number ASC',
        (task_id,)
    )

    # Convert rows to EvolutionAttempt objects
    attempts = [EvolutionAttempt.from_row(row) for row in rows]

    # Convert to dicts (keeping metrics_json as dict, not string)
    attempts_dicts = []
    for attempt in attempts:
        # Create dict manually to preserve metrics_json as dict
        attempt_dict = {
            'id': attempt.id,
            'session_id': attempt.session_id,
            'task_id': attempt.task_id,
            'attempt_number': attempt.attempt_number,
            'metrics_json': attempt.metrics_json if include_metrics else None,
            'outcome': attempt.outcome,
            'created_at': attempt.created_at
        }
        attempts_dicts.append(attempt_dict)

    # Calculate summary
    summary = {
        'total_attempts': len(attempts),
        'success_count': sum(1 for a in attempts if a.outcome == 'SUCCESS'),
        'failure_count': sum(1 for a in attempts if a.outcome == 'FAILURE'),
        'partial_count': sum(1 for a in attempts if a.outcome == 'PARTIAL')
    }

    # Find best attempt (based on metrics if available)
    best_attempt = None
    attempts_with_metrics = [a for a in attempts if a.metrics_json and 'tests_passed' in a.metrics_json]
    if attempts_with_metrics:
        best_attempt_obj = max(attempts_with_metrics, key=lambda a: a.metrics_json.get('tests_passed', 0))
        best_attempt = best_attempt_obj.to_dict()
        # Include deserialized metrics in best_attempt
        best_attempt['metrics'] = best_attempt_obj.metrics_json

    # Determine pattern (IMPROVING/DECLINING/STABLE/UNKNOWN)
    pattern = _analyze_pattern(attempts)

    # Build result
    result = {
        'task_id': task_id,
        'total_attempts': len(attempts),
        'attempts': attempts_dicts,
        'summary': summary,
        'best_attempt': best_attempt,
        'pattern': pattern,
        'retrieved_at': datetime.now(timezone.utc).isoformat()
    }

    logger.info("Evolution context retrieved", extra={
        'tool_name': 'get_evolution_context',
        'task_id': task_id,
        'total_attempts': len(attempts),
        'pattern': pattern
    })

    return result


def _analyze_pattern(attempts: List[EvolutionAttempt]) -> str:
    """
    Analyze the pattern of evolution attempts.

    Args:
        attempts: List of EvolutionAttempt objects

    Returns:
        Pattern string: 'IMPROVING', 'DECLINING', 'STABLE', or 'UNKNOWN'
    """
    # Need at least 2 attempts to determine a pattern
    if len(attempts) < 2:
        return 'UNKNOWN'

    # Extract metrics with tests_passed for pattern analysis
    attempts_with_metrics = [
        a for a in attempts
        if a.metrics_json and 'tests_passed' in a.metrics_json
    ]

    # Need at least 2 attempts with metrics
    if len(attempts_with_metrics) < 2:
        return 'UNKNOWN'

    # Calculate trend based on tests_passed
    tests_passed_values = [a.metrics_json['tests_passed'] for a in attempts_with_metrics]

    # Calculate average change
    changes = []
    for i in range(1, len(tests_passed_values)):
        change = tests_passed_values[i] - tests_passed_values[i-1]
        changes.append(change)

    avg_change = sum(changes) / len(changes)

    # Determine pattern based on average change
    if avg_change > 1:
        return 'IMPROVING'
    elif avg_change < -1:
        return 'DECLINING'
    else:
        return 'STABLE'
