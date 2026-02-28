"""
Prusti verification MCP tool.

Runs 'cargo prusti' on Rust projects to verify pre/post-conditions
and invariants using Prusti (a Rust verification tool based on Viper).

Follows the register_tools(mcp, db) pattern from existing Gatekeeper tools.

Usage (registered by server_v3.py):
    from gatekeeper_evolve_mcp.tools import prusti
    prusti.register_tools(mcp, db)
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastmcp import FastMCP

from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.models import VerificationResult
from gatekeeper_evolve_mcp.tools.verification_runner import run_subprocess
from gatekeeper_evolve_mcp.tools.prusti_parser import (
    parse_prusti_errors,
    parse_prusti_counterexamples,
)

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None


def register_tools(mcp: FastMCP, db: DatabaseManager) -> None:
    """Register Prusti verification tools with the MCP server."""
    global _db
    _db = db
    mcp.tool()(verify_prusti)


async def verify_prusti(
    session_id: str,
    source_file: str,
    project_dir: str,
) -> Dict[str, Any]:
    """
    Run Prusti verification on a Rust project.

    Executes 'cargo prusti' in the project directory with
    PRUSTI_COUNTEREXAMPLE=true to enable counterexample output.
    Parses the rustc-style stderr for errors and counterexamples.

    Args:
        session_id: Gatekeeper session ID for tracking
        source_file: Path to the Rust source file being verified (for context)
        project_dir: Path to the Rust project directory (where Cargo.toml lives)

    Returns:
        Dict from VerificationResult.to_dict() with keys:
        - status: 'pass', 'fail', or 'error'
        - result_json: JSON string with errors, counterexamples, checks, raw_output
    """
    logger.info(f"Running Prusti verification", extra={
        'session_id': session_id,
        'source_file': source_file,
        'project_dir': project_dir,
    })

    # Run cargo prusti with counterexample output enabled
    result = await run_subprocess(
        cmd=['cargo', 'prusti'],
        cwd=project_dir,
        env={'PRUSTI_COUNTEREXAMPLE': 'true'},
        timeout=120,
    )

    # Determine status from exit code and timeout
    if result.timed_out:
        status = 'error'
        errors = []
        counterexamples = []
        raw_output = f"Prusti timed out after 120s. stderr: {result.stderr}"
    elif result.returncode == 0:
        status = 'pass'
        errors = []
        counterexamples = []
        raw_output = result.stderr
    elif result.returncode == 101:
        # Prusti internal error (ICE)
        status = 'error'
        errors = parse_prusti_errors(result.stderr)
        counterexamples = []
        raw_output = result.stderr
    elif result.returncode == 1:
        # Verification failure -- parse errors and counterexamples
        status = 'fail'
        errors = parse_prusti_errors(result.stderr)
        counterexamples = parse_prusti_counterexamples(result.stderr)
        raw_output = result.stderr
    else:
        # Unexpected exit code
        status = 'error'
        errors = parse_prusti_errors(result.stderr)
        counterexamples = []
        raw_output = f"Unexpected exit code {result.returncode}. stderr: {result.stderr}"

    # Construct VerificationResult
    vr = VerificationResult(
        id=None,
        session_id=session_id,
        tool='prusti',
        status=status,
        errors=errors,
        counterexamples=counterexamples,
        checks=[],  # Prusti does not produce per-check results (that's Kani)
        raw_output=raw_output,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # Store in database
    if _db is not None:
        data = vr.to_dict()
        try:
            row_id = _db.insert('verification_results', {
                'session_id': data['session_id'],
                'tool': data['tool'],
                'status': data['status'],
                'result_json': data['result_json'],
                'created_at': data['created_at'],
            })
            vr.id = row_id
            logger.info(f"Stored Prusti result id={row_id}", extra={
                'session_id': session_id,
                'status': status,
            })
        except Exception as e:
            logger.error(f"Failed to store Prusti result: {e}", extra={
                'session_id': session_id,
            })
    else:
        logger.warning("No database configured, result not stored")

    return vr.to_dict()
