"""
Kani verification MCP tool.

Runs 'cargo kani --harness <name>' on Rust projects to verify proof harnesses
using Kani (a Rust model checker based on CBMC).

Follows the register_tools(mcp, db) pattern from existing Gatekeeper tools.

Key differences from Prusti:
- Parses stdout (not stderr) for RESULTS section with per-check granularity
- Uses VerificationCheck objects for per-check results (SUCCESS/FAILURE/UNREACHABLE)
- Accepts harness_name and optional unwind parameters
- Re-runs with --concrete-playback=print when failures detected to capture counterexamples

Usage (registered by server_v3.py):
    from gatekeeper_evolve_mcp.tools import kani
    kani.register_tools(mcp, db)
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastmcp import FastMCP

from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.models import VerificationResult, VerificationCheck
from gatekeeper_evolve_mcp.tools.verification_runner import run_subprocess
from gatekeeper_evolve_mcp.tools.kani_parser import (
    parse_kani_results,
    parse_kani_verification_status,
    parse_kani_counterexamples,
)

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None


def register_tools(mcp: FastMCP, db: DatabaseManager) -> None:
    """Register Kani verification tools with the MCP server."""
    global _db
    _db = db
    mcp.tool()(verify_kani)


async def verify_kani(
    session_id: str,
    source_file: str,
    harness_name: str,
    project_dir: str,
    unwind: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run Kani verification on a specific proof harness.

    Executes 'cargo kani --harness <harness_name>' in the project directory.
    Parses the RESULTS section from stdout for per-check results.
    When any check fails, re-runs with --concrete-playback=print to capture
    counterexample traces.

    Args:
        session_id: Gatekeeper session ID for tracking
        source_file: Path to the Rust source file containing the harness (for context)
        harness_name: Name of the Kani proof harness to run (e.g., 'verify_add')
        project_dir: Path to the Rust project directory (where Cargo.toml lives)
        unwind: Optional loop unwinding bound (passed as --unwind <n>)

    Returns:
        Dict from VerificationResult.to_dict() with keys:
        - status: 'pass', 'fail', or 'error'
        - result_json: JSON string with errors, counterexamples, checks, raw_output
    """
    logger.info(f"Running Kani verification for harness '{harness_name}'", extra={
        'session_id': session_id,
        'source_file': source_file,
        'harness_name': harness_name,
        'project_dir': project_dir,
        'unwind': unwind,
    })

    # Build the command
    cmd = ['cargo', 'kani', '--harness', harness_name]
    if unwind is not None:
        cmd.extend(['--unwind', str(unwind)])

    # Run cargo kani
    result = await run_subprocess(
        cmd=cmd,
        cwd=project_dir,
        timeout=120,
    )

    # Handle timeout
    if result.timed_out:
        status = 'error'
        checks = []
        counterexamples = []
        errors = []
        raw_output = f"Kani timeout after 120s. stdout: {result.stdout[:500]}. stderr: {result.stderr[:500]}"
    else:
        # Parse stdout for check results and overall status
        check_dicts = parse_kani_results(result.stdout)
        verification_status = parse_kani_verification_status(result.stdout)

        # Build VerificationCheck objects
        checks = [
            VerificationCheck(
                check_name=c['check_name'],
                status=c['status'],
                message=c['message'],
            )
            for c in check_dicts
        ]

        # Determine overall status
        if result.returncode != 0 and not check_dicts and not verification_status:
            # Non-zero exit with no parseable results = error (e.g., invalid harness name,
            # compilation failure, Kani not installed)
            status = 'error'
            errors = [{'message': f'Kani exited with code {result.returncode} but produced no parseable results', 'stderr': result.stderr[:1000]}]
            counterexamples = []
            raw_output = f"stdout: {result.stdout}\nstderr: {result.stderr}"
        else:
            # Derive status from per-check results
            has_failure = any(c.status == 'FAILURE' for c in checks)

            if has_failure:
                status = 'fail'
            elif verification_status == 'FAILED':
                status = 'fail'
            elif verification_status == 'SUCCESSFUL':
                status = 'pass'
            elif checks and all(c.status in ('SUCCESS', 'UNREACHABLE') for c in checks):
                status = 'pass'
            elif result.returncode == 0:
                status = 'pass'
            else:
                status = 'error'

            errors = []
            raw_output = result.stdout

            # When failures detected, re-run with --concrete-playback=print for counterexamples
            counterexamples = []
            if has_failure:
                logger.info(f"Failures detected, re-running with --concrete-playback=print", extra={
                    'session_id': session_id,
                    'harness_name': harness_name,
                })
                playback_cmd = cmd + ['--concrete-playback=print']
                playback_result = await run_subprocess(
                    cmd=playback_cmd,
                    cwd=project_dir,
                    timeout=120,
                )
                if not playback_result.timed_out:
                    counterexamples = parse_kani_counterexamples(playback_result.stdout)
                    # Append playback output to raw_output for debugging
                    raw_output += f"\n\n--- Concrete Playback Output ---\n{playback_result.stdout}"

    # Construct VerificationResult
    vr = VerificationResult(
        id=None,
        session_id=session_id,
        tool='kani',
        status=status,
        errors=errors,
        counterexamples=counterexamples,
        checks=checks,
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
            logger.info(f"Stored Kani result id={row_id}", extra={
                'session_id': session_id,
                'status': status,
                'num_checks': len(checks),
            })
        except Exception as e:
            logger.error(f"Failed to store Kani result: {e}", extra={
                'session_id': session_id,
            })
    else:
        logger.warning("No database configured, result not stored")

    return vr.to_dict()
