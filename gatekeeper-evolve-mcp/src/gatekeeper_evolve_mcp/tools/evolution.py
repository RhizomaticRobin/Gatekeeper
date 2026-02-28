"""
Evolution tracking MCP tools for Gatekeeper Evolve server.

Provides tools for:
- record_evolution_attempt: Track evolution/retry attempts for a task (writes to approaches table)
- get_evolution_context: Retrieve historical attempts and pattern analysis
"""

import logging
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, TYPE_CHECKING

from fastmcp import FastMCP
from gatekeeper_evolve_mcp.models import Approach
from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.validators import validate_session_id, ValidationError

if TYPE_CHECKING:
    from gatekeeper_evolve_mcp.state_writer import StateWriter

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None
_state_writer: Optional["StateWriter"] = None

VALID_OUTCOMES = {'SUCCESS', 'FAILURE', 'PARTIAL'}


def register_tools(mcp: FastMCP, db: DatabaseManager, state_writer: Optional["StateWriter"] = None) -> None:
    """Register evolution tools with FastMCP server."""
    global _db, _state_writer
    _db = db
    _state_writer = state_writer
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

    Writes to the unified approaches table with evolution tracking fields.

    Args:
        task_id: Task identifier (e.g., "2.1", "3.5")
        attempt_number: Sequential attempt number (1, 2, 3, ...)
        outcome: Outcome of the attempt ('SUCCESS', 'FAILURE', 'PARTIAL')
        metrics: Optional dict with test metrics (tests_passed, coverage, etc.)
        session_id: Optional session ID to link attempt to

    Returns:
        Dict containing approach fields
    """
    outcome_upper = outcome.upper()
    if outcome_upper not in VALID_OUTCOMES:
        raise ValueError(f"Invalid outcome '{outcome}'. Must be one of {VALID_OUTCOMES}")

    if session_id is not None:
        try:
            validate_session_id(session_id)
        except ValidationError as e:
            raise ValueError(str(e))
        session_exists = _db.fetchone(
            'SELECT session_id FROM sessions WHERE session_id = ?', (session_id,)
        )
        if not session_exists:
            raise ValueError(f"Session '{session_id}' does not exist.")

    # Check for duplicate attempt
    existing = _db.fetchone(
        'SELECT id FROM approaches WHERE task_id = ? AND attempt_number = ?',
        (task_id, attempt_number)
    )
    if existing:
        raise ValueError(
            f"Evolution attempt with task_id '{task_id}' and attempt_number {attempt_number} already exists"
        )

    created_at = datetime.now(timezone.utc).isoformat()
    approach_id = str(uuid.uuid4())

    approach_data = {
        'id': approach_id,
        'prompt_addendum': f"attempt #{attempt_number}: {outcome_upper}",
        'parent_id': None,
        'generation': attempt_number - 1,
        'metrics_json': json.dumps(metrics) if metrics else None,
        'island': 0,
        'feature_coords': None,
        'task_id': task_id,
        'task_type': 'evolution_attempt',
        'file_patterns': None,
        'artifacts_json': None,
        'timestamp': time.time(),
        'iteration': attempt_number,
        'session_id': session_id,
        'outcome': outcome_upper,
        'attempt_number': attempt_number,
        'created_at': created_at,
    }

    try:
        _db.insert('approaches', approach_data)

        row = _db.fetchone('SELECT * FROM approaches WHERE id = ?', (approach_id,))
        approach = Approach.from_row(row)

        if _state_writer and session_id:
            try:
                _state_writer.write_state_files(session_id)
            except Exception as e:
                logger.error(f"Failed to write state files: {e}", extra={'tool_name': 'record_evolution_attempt'})

        return approach.to_dict()

    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise RuntimeError(f"Failed to record evolution attempt: {e}")


def get_evolution_context(
    task_id: str,
    include_metrics: bool = True
) -> Dict[str, Any]:
    """
    Get evolution context for a task, including all historical attempts.

    Args:
        task_id: Task identifier
        include_metrics: Whether to include metrics in the response

    Returns:
        Dict with task_id, total_attempts, attempts, summary, best_attempt, pattern
    """
    rows = _db.fetchall(
        'SELECT * FROM approaches WHERE task_id = ? ORDER BY attempt_number ASC, created_at ASC',
        (task_id,)
    )

    approaches = [Approach.from_row(row) for row in rows]

    attempts_dicts = []
    for a in approaches:
        attempt_dict = {
            'id': a.id,
            'session_id': a.session_id,
            'task_id': a.task_id,
            'attempt_number': a.attempt_number,
            'metrics': a.metrics if include_metrics else None,
            'outcome': a.outcome,
            'created_at': a.created_at
        }
        attempts_dicts.append(attempt_dict)

    summary = {
        'total_attempts': len(approaches),
        'success_count': sum(1 for a in approaches if a.outcome == 'SUCCESS'),
        'failure_count': sum(1 for a in approaches if a.outcome == 'FAILURE'),
        'partial_count': sum(1 for a in approaches if a.outcome == 'PARTIAL')
    }

    best_attempt = None
    attempts_with_metrics = [a for a in approaches if a.metrics and 'tests_passed' in a.metrics]
    if attempts_with_metrics:
        best_obj = max(attempts_with_metrics, key=lambda a: a.metrics.get('tests_passed', 0))
        best_attempt = best_obj.to_dict()

    pattern = _analyze_pattern(approaches)

    return {
        'task_id': task_id,
        'total_attempts': len(approaches),
        'attempts': attempts_dicts,
        'summary': summary,
        'best_attempt': best_attempt,
        'pattern': pattern,
        'retrieved_at': datetime.now(timezone.utc).isoformat()
    }


def _analyze_pattern(approaches: List[Approach]) -> str:
    """Analyze the pattern of evolution attempts."""
    if len(approaches) < 2:
        return 'UNKNOWN'

    with_metrics = [a for a in approaches if a.metrics and 'tests_passed' in a.metrics]
    if len(with_metrics) < 2:
        return 'UNKNOWN'

    values = [a.metrics['tests_passed'] for a in with_metrics]
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    avg_change = sum(changes) / len(changes)

    if avg_change > 1:
        return 'IMPROVING'
    elif avg_change < -1:
        return 'DECLINING'
    else:
        return 'STABLE'
