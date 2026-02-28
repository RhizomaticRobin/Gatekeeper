"""
Python contract verification MCP tool.

Validates icontract decorators exist on Python functions and runs
CrossHair for symbolic verification of those contracts.

Follows the register_tools(mcp, db) pattern from existing Gatekeeper tools.

Usage (registered by server_v3.py):
    from gatekeeper_evolve_mcp.tools import python_contracts
    python_contracts.register_tools(mcp, db)
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastmcp import FastMCP

from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.models import VerificationResult
from gatekeeper_evolve_mcp.tools.verification_runner import run_subprocess
from gatekeeper_evolve_mcp.tools.python_contracts_parser import (
    parse_crosshair_output,
    check_icontract_decorators,
)

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None


def register_tools(mcp: FastMCP, db: DatabaseManager) -> None:
    """Register Python contract verification tools with the MCP server."""
    global _db
    _db = db
    mcp.tool()(verify_python_contracts)


async def verify_python_contracts(
    session_id: str,
    source_file: str,
) -> Dict[str, Any]:
    """
    Verify Python contracts using CrossHair symbolic execution.

    First validates that icontract decorators (@require/@ensure) exist in the
    source file. If no decorators are found, returns an error immediately without
    running CrossHair (since there would be nothing to verify).

    If decorators are present, runs 'crosshair check <source_file>' and parses
    the mypy-format output for contract violations.

    Args:
        session_id: Gatekeeper session ID for tracking
        source_file: Path to the Python source file to verify

    Returns:
        Dict from VerificationResult.to_dict() with keys:
        - status: 'pass', 'fail', or 'error'
        - result_json: JSON string with errors, counterexamples, checks, raw_output
    """
    logger.info(f"Running Python contract verification", extra={
        'session_id': session_id,
        'source_file': source_file,
    })

    # Step 1: Read the source file and check for icontract decorators
    source_path = Path(source_file)
    try:
        source_text = source_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        vr = _build_result(
            session_id=session_id,
            status='error',
            errors=[{'message': f'Source file not found: {source_file}'}],
            raw_output=f'FileNotFoundError: {source_file}',
        )
        return _store_and_return(vr)
    except Exception as e:
        vr = _build_result(
            session_id=session_id,
            status='error',
            errors=[{'message': f'Failed to read source file: {e}'}],
            raw_output=str(e),
        )
        return _store_and_return(vr)

    # Check for icontract decorators
    decorator_info = check_icontract_decorators(source_text)

    if not decorator_info['has_require'] and not decorator_info['has_ensure']:
        # No icontract decorators found -- return error without running CrossHair
        logger.warning(f"No icontract decorators found in {source_file}", extra={
            'session_id': session_id,
        })
        vr = _build_result(
            session_id=session_id,
            status='error',
            errors=[{
                'message': (
                    f'No icontract decorators (@require/@ensure) found in {source_file}. '
                    'CrossHair requires icontract decorators to verify contracts.'
                ),
            }],
            raw_output=f'No icontract decorators found. decorator_info={decorator_info}',
        )
        return _store_and_return(vr)

    # Step 2: Run CrossHair
    result = await run_subprocess(
        cmd=['crosshair', 'check', source_file],
        timeout=120,
    )

    # Determine status from exit code and timeout
    if result.timed_out:
        status = 'error'
        errors = []
        counterexamples = []
        raw_output = f"CrossHair timed out after 120s. stdout: {result.stdout[:500]}. stderr: {result.stderr[:500]}"
    elif result.returncode == 0:
        status = 'pass'
        errors = []
        counterexamples = []
        raw_output = result.stdout if result.stdout else 'All contracts satisfied.'
    elif result.returncode == 1:
        # Contract violation found -- parse output
        status = 'fail'
        parsed_errors = parse_crosshair_output(result.stdout)
        errors = parsed_errors
        # Extract counterexamples from error messages (CrossHair includes them inline)
        counterexamples = []
        for err in parsed_errors:
            if 'counterexample' in err.get('message', '').lower():
                counterexamples.append({
                    'file': err['file'],
                    'line': err['line'],
                    'description': err['message'],
                })
        raw_output = result.stdout
    elif result.returncode == 2:
        # CrossHair error (parse error, missing dependency, etc.)
        status = 'error'
        errors = parse_crosshair_output(result.stdout) if result.stdout else []
        counterexamples = []
        raw_output = f"CrossHair exited with code 2. stdout: {result.stdout}. stderr: {result.stderr}"
    else:
        # Unexpected exit code
        status = 'error'
        errors = []
        counterexamples = []
        raw_output = f"Unexpected exit code {result.returncode}. stdout: {result.stdout}. stderr: {result.stderr}"

    vr = _build_result(
        session_id=session_id,
        status=status,
        errors=errors,
        counterexamples=counterexamples,
        raw_output=raw_output,
    )

    return _store_and_return(vr)


def _build_result(
    session_id: str,
    status: str,
    errors: list = None,
    counterexamples: list = None,
    raw_output: str = '',
) -> VerificationResult:
    """Build a VerificationResult for the CrossHair tool."""
    return VerificationResult(
        id=None,
        session_id=session_id,
        tool='crosshair',
        status=status,
        errors=errors or [],
        counterexamples=counterexamples or [],
        checks=[],  # CrossHair does not produce per-check results
        raw_output=raw_output,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _store_and_return(vr: VerificationResult) -> dict:
    """Store a VerificationResult in the DB and return its to_dict()."""
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
            logger.info(f"Stored CrossHair result id={row_id}", extra={
                'session_id': vr.session_id,
                'status': vr.status,
            })
        except Exception as e:
            logger.error(f"Failed to store CrossHair result: {e}", extra={
                'session_id': vr.session_id,
            })
    else:
        logger.warning("No database configured, result not stored")

    return vr.to_dict()
