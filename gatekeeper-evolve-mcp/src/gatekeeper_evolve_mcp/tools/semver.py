"""
Semver compatibility checking MCP tool.

Runs 'cargo semver-checks check-release --baseline-rev <rev>' on Rust projects
to detect breaking API changes between the current code and a baseline revision.

Follows the register_tools(mcp, db) pattern from existing Gatekeeper tools.

Usage (registered by server_v3.py):
    from gatekeeper_evolve_mcp.tools import semver
    semver.register_tools(mcp, db)
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastmcp import FastMCP

from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.models import VerificationResult
from gatekeeper_evolve_mcp.tools.verification_runner import run_subprocess
from gatekeeper_evolve_mcp.tools.semver_parser import parse_semver_breaking_changes

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None


def register_tools(mcp: FastMCP, db: DatabaseManager) -> None:
    """Register semver compatibility checking tools with the MCP server."""
    global _db
    _db = db
    mcp.tool()(check_semver_compat)


async def check_semver_compat(
    session_id: str,
    project_dir: str,
    baseline_rev: str,
) -> Dict[str, Any]:
    """
    Check semver compatibility of a Rust project against a baseline revision.

    Executes 'cargo semver-checks check-release --baseline-rev <rev>' in the
    project directory and parses the output for breaking API changes.

    Args:
        session_id: Gatekeeper session ID for tracking
        project_dir: Path to the Rust project directory (where Cargo.toml lives)
        baseline_rev: Git revision to compare against (e.g., 'v1.0.0', 'main', a commit SHA)

    Returns:
        Dict from VerificationResult.to_dict() with keys:
        - status: 'pass', 'fail', or 'error'
        - result_json: JSON string with errors (breaking changes), counterexamples, checks, raw_output
    """
    logger.info(f"Running semver compatibility check", extra={
        'session_id': session_id,
        'project_dir': project_dir,
        'baseline_rev': baseline_rev,
    })

    # Run cargo semver-checks
    result = await run_subprocess(
        cmd=['cargo', 'semver-checks', 'check-release', '--baseline-rev', baseline_rev],
        cwd=project_dir,
        timeout=120,
    )

    # Determine status from exit code and timeout
    if result.timed_out:
        status = 'error'
        errors = []
        raw_output = f"semver-checks timed out after 120s. stdout: {result.stdout[:500]}. stderr: {result.stderr[:500]}"
    elif result.returncode == 0:
        status = 'pass'
        errors = []
        raw_output = result.stdout
    elif result.returncode == 1:
        # Breaking changes detected -- parse them
        status = 'fail'
        errors = parse_semver_breaking_changes(result.stdout)
        raw_output = result.stdout
    elif result.returncode == 2:
        # semver-checks error (invalid baseline rev, missing Cargo.toml, etc.)
        status = 'error'
        errors = []
        raw_output = f"semver-checks exited with code 2. stdout: {result.stdout}. stderr: {result.stderr}"
    else:
        # Unexpected exit code
        status = 'error'
        errors = []
        raw_output = f"Unexpected exit code {result.returncode}. stdout: {result.stdout}. stderr: {result.stderr}"

    # Construct VerificationResult
    vr = VerificationResult(
        id=None,
        session_id=session_id,
        tool='semver',
        status=status,
        errors=errors,
        counterexamples=[],  # semver-checks does not produce counterexamples
        checks=[],  # semver-checks does not produce per-check results
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
            logger.info(f"Stored semver result id={row_id}", extra={
                'session_id': session_id,
                'status': status,
            })
        except Exception as e:
            logger.error(f"Failed to store semver result: {e}", extra={
                'session_id': session_id,
            })
    else:
        logger.warning("No database configured, result not stored")

    return vr.to_dict()
