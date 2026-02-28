"""
MCP tool for checking contract composability via z3 implication checking.

Verifies that module A's postconditions logically imply module B's preconditions
at call sites. Uses z3-solver Python bindings directly (NOT subprocess).

This is the MCP tool wrapper. The core z3 logic lives in z3_checker.py.

Usage via MCP:
    check_composability(
        session_id="gk_20260228_abc01",
        postconditions=["x > 0", "y >= x"],
        preconditions=["x > 0"],
        variables={"x": "Int", "y": "Int"},
        timeout_ms=5000
    )
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastmcp import FastMCP

from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.models import VerificationResult
from gatekeeper_evolve_mcp.tools.z3_checker import check_implication, CheckResult

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None


def register_tools(mcp: FastMCP, db: DatabaseManager) -> None:
    """Register composability checking tools with the MCP server."""
    global _db
    _db = db
    mcp.tool()(check_composability)


async def check_composability(
    session_id: str,
    postconditions: list[str],
    preconditions: list[str],
    variables: dict[str, str],
    timeout_ms: int = 5000
) -> Dict[str, Any]:
    """
    Check if postconditions logically imply preconditions (contract composability).

    Uses z3 SMT solver to verify that AND(postconditions) => AND(preconditions).
    This is the core composability check: if module A guarantees its postconditions,
    can module B rely on its preconditions being satisfied?

    Args:
        session_id: Gatekeeper session ID for result tracking
        postconditions: List of z3-parseable expression strings (module A's guarantees)
        preconditions: List of z3-parseable expression strings (module B's requirements)
        variables: Dict mapping variable names to types ('Int', 'Real', 'Bool')
        timeout_ms: Solver timeout in milliseconds (default: 5000)

    Returns:
        Dict representation of VerificationResult:
        - status='pass': Composable (postconditions DO imply preconditions)
        - status='fail': Not composable (counterexample found)
        - status='error': Timeout or parse failure
    """
    logger.info(
        f"Checking composability for session {session_id}: "
        f"{len(postconditions)} postconditions, {len(preconditions)} preconditions",
        extra={'tool_name': 'composability', 'session_id': session_id}
    )

    # Run the z3 implication check
    check_result = check_implication(
        postconditions=postconditions,
        preconditions=preconditions,
        variables=variables,
        timeout_ms=timeout_ms
    )

    # Map CheckResult to VerificationResult
    errors = []
    counterexamples = []
    raw_output_parts = []

    raw_output_parts.append(f"Postconditions: {postconditions}")
    raw_output_parts.append(f"Preconditions: {preconditions}")
    raw_output_parts.append(f"Variables: {variables}")
    raw_output_parts.append(f"Timeout: {timeout_ms}ms")
    raw_output_parts.append(f"Result: {check_result.status}")

    if check_result.status == 'fail' and check_result.counterexample:
        counterexamples.append(check_result.counterexample)
        raw_output_parts.append(f"Counterexample: {check_result.counterexample}")

    if check_result.status == 'error' and check_result.error_message:
        errors.append({
            'message': check_result.error_message,
            'type': 'timeout' if 'timeout' in check_result.error_message else 'parse_error'
        })
        raw_output_parts.append(f"Error: {check_result.error_message}")

    raw_output = "\n".join(raw_output_parts)

    verification_result = VerificationResult(
        id=None,
        session_id=session_id,
        tool='composability',
        status=check_result.status,
        errors=errors,
        counterexamples=counterexamples,
        checks=[],  # Composability has no per-check granularity
        raw_output=raw_output,
        created_at=datetime.now(timezone.utc).isoformat()
    )

    # Store in database
    if _db is not None:
        data = verification_result.to_dict()
        try:
            row_id = _db.insert('verification_results', {
                'session_id': data['session_id'],
                'tool': data['tool'],
                'status': data['status'],
                'result_json': data['result_json'],
                'created_at': data['created_at'],
            })
            logger.info(
                f"Stored composability result (id={row_id}) for session {session_id}",
                extra={'tool_name': 'composability', 'row_id': row_id}
            )
        except Exception as e:
            logger.error(
                f"Failed to store composability result: {e}",
                extra={'tool_name': 'composability', 'session_id': session_id}
            )

    return verification_result.to_dict()
