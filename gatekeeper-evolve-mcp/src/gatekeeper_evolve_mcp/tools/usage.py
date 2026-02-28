"""
Usage metrics MCP tools for Gatekeeper Evolve server.

Provides tools for:
- record_usage: Record token usage and cost for a session
- get_session_usage: Query usage metrics for a session
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastmcp import FastMCP
from gatekeeper_evolve_mcp.models import UsageMetric
from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.validators import validate_session_id, ValidationError

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None


def register_tools(mcp: FastMCP, db: DatabaseManager) -> None:
    """Register usage metrics tools with FastMCP server."""
    global _db
    _db = db
    mcp.tool()(record_usage)
    mcp.tool()(get_session_usage)
    logger.info("Usage tools registered", extra={'tool_name': 'usage'})


def record_usage(
    session_id: str,
    tool_name: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost_estimate: Optional[float] = None
) -> Dict[str, Any]:
    """
    Record token usage and cost for a session.

    Args:
        session_id: Session identifier to record usage for
        tool_name: Name of the MCP tool
        input_tokens: Number of input tokens consumed
        output_tokens: Number of output tokens generated
        cost_estimate: Estimated cost in dollars

    Returns:
        Dict containing UsageMetric fields
    """
    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    session_row = _db.fetchone('SELECT session_id FROM sessions WHERE session_id = ?', (session_id,))
    if not session_row:
        raise ValueError(f"Session '{session_id}' not found")

    created_at = datetime.now(timezone.utc).isoformat()
    usage_data = {
        'session_id': session_id,
        'tool_name': tool_name,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'cost_estimate': cost_estimate,
        'created_at': created_at
    }

    row_id = _db.insert('usage_metrics', usage_data)
    row = _db.fetchone('SELECT * FROM usage_metrics WHERE id = ?', (row_id,))
    return UsageMetric.from_row(row).to_dict()


def get_session_usage(session_id: str) -> Dict[str, Any]:
    """Get usage metrics summary for a session."""
    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    session_row = _db.fetchone('SELECT session_id FROM sessions WHERE session_id = ?', (session_id,))
    if not session_row:
        raise ValueError(f"Session '{session_id}' not found")

    rows = _db.fetchall(
        'SELECT * FROM usage_metrics WHERE session_id = ? ORDER BY created_at ASC',
        (session_id,)
    )

    metrics = []
    total_input = 0
    total_output = 0
    total_cost = 0.0
    by_tool: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        metric = UsageMetric.from_row(row)
        metrics.append(metric.to_dict())

        if metric.input_tokens is not None:
            total_input += metric.input_tokens
        if metric.output_tokens is not None:
            total_output += metric.output_tokens
        if metric.cost_estimate is not None:
            total_cost += metric.cost_estimate

        if metric.tool_name not in by_tool:
            by_tool[metric.tool_name] = {
                'count': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost_estimate': 0.0
            }
        by_tool[metric.tool_name]['count'] += 1
        if metric.input_tokens is not None:
            by_tool[metric.tool_name]['input_tokens'] += metric.input_tokens
        if metric.output_tokens is not None:
            by_tool[metric.tool_name]['output_tokens'] += metric.output_tokens
        if metric.cost_estimate is not None:
            by_tool[metric.tool_name]['cost_estimate'] += metric.cost_estimate

    return {
        'session_id': session_id,
        'metrics': metrics,
        'total_input_tokens': total_input,
        'total_output_tokens': total_output,
        'total_cost_estimate': round(total_cost, 6),
        'by_tool': by_tool,
        'metric_count': len(metrics)
    }
