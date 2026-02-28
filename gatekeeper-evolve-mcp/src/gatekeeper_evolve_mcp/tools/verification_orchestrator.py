"""Verification orchestrator that dispatches to individual tools based on VerificationLevel."""
import json
import logging
from typing import Any, Dict, List, Optional

from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.verification_config import (
    VerificationLevel, get_tools_for_level, parse_verification_level
)
from gatekeeper_evolve_mcp.tools.signals import record_agent_signal

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None

# Tool dispatch map: tool name -> callable
# Populated lazily to avoid circular imports
_TOOL_DISPATCH: Dict[str, Any] = {}


def _get_tool_dispatch() -> Dict[str, Any]:
    """Lazily build tool dispatch map to avoid circular imports."""
    if not _TOOL_DISPATCH:
        from gatekeeper_evolve_mcp.tools.prusti import verify_prusti
        from gatekeeper_evolve_mcp.tools.kani import verify_kani
        from gatekeeper_evolve_mcp.tools.semver import check_semver_compat
        from gatekeeper_evolve_mcp.tools.python_contracts import verify_python_contracts
        from gatekeeper_evolve_mcp.tools.composability import check_composability
        _TOOL_DISPATCH['prusti'] = verify_prusti
        _TOOL_DISPATCH['kani'] = verify_kani
        _TOOL_DISPATCH['semver'] = check_semver_compat
        _TOOL_DISPATCH['crosshair'] = verify_python_contracts
        _TOOL_DISPATCH['composability'] = check_composability
    return _TOOL_DISPATCH


def _extract_suggested_fix_areas(errors: list) -> List[str]:
    """Extract file:line references from error dicts for suggested fix areas.

    Checks for 'file'/'line' keys (Prusti/Kani style) and
    'span_file'/'span_line' keys (semver style).
    Returns a list of 'file:line' strings.
    """
    areas = []
    for error in errors:
        if isinstance(error, dict):
            # Check 'file'/'line' keys first
            if "file" in error and "line" in error:
                file_val = error["file"]
                line_val = error["line"]
                if file_val is not None and line_val is not None:
                    areas.append(f"{file_val}:{line_val}")
            # Check 'span_file'/'span_line' keys
            elif "span_file" in error and "span_line" in error:
                span_file = error["span_file"]
                span_line = error["span_line"]
                if span_file is not None and span_line is not None:
                    areas.append(f"{span_file}:{span_line}")
    return areas


def _build_fail_context(tool_name: str, result: dict) -> dict:
    """Build structured context_json for VERIFICATION_FAIL signal.

    Args:
        tool_name: Name of the tool that failed (e.g., 'prusti', 'kani', 'semver')
        result: The dict returned by the tool (from VerificationResult.to_dict())

    Returns:
        Dict with keys: tool, status, errors, suggested_fix_areas
    """
    # Extract errors from result_json if present
    errors = []
    result_json_str = result.get("result_json")
    if result_json_str:
        try:
            result_data = json.loads(result_json_str)
            errors = result_data.get("errors", [])
        except (json.JSONDecodeError, TypeError):
            errors = []

    suggested_fix_areas = _extract_suggested_fix_areas(errors)

    return {
        "tool": tool_name,
        "status": "fail",
        "errors": errors,
        "suggested_fix_areas": suggested_fix_areas,
    }


async def run_verification(
    session_id: str,
    verification_level: str,
    source_file: str,
    project_dir: str,
    harness_name: Optional[str] = None,
    baseline_rev: Optional[str] = None,
    postconditions: Optional[List[str]] = None,
    preconditions: Optional[List[str]] = None,
    variables: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run verification at the specified level, dispatching to appropriate tools.

    Args:
        session_id: Gatekeeper session ID for tracking
        verification_level: Level string (tests_only, prusti, kani, crosshair, full, full_python) — case-insensitive
        source_file: Path to the source file to verify
        project_dir: Path to the project directory
        harness_name: Optional Kani proof harness name (required for kani/full levels)
        baseline_rev: Optional baseline git revision for semver checks (required for full level)
        postconditions: Optional list of z3-parseable postcondition strings (for composability checks)
        preconditions: Optional list of z3-parseable precondition strings (for composability checks)
        variables: Optional dict mapping variable names to z3 types (for composability checks)

    Returns:
        Dict with keys:
        - overall_status: 'pass', 'fail', or 'error'
        - verification_level: The parsed verification level string
        - results: List of individual tool result dicts
        - signal_recorded: True if a signal was recorded, False otherwise

    Raises:
        ValueError: If verification_level is not a valid VerificationLevel value
    """
    # Validate and parse the verification level (raises ValueError if invalid)
    level = parse_verification_level(verification_level)

    # Get the list of tool names to dispatch for this level
    tool_names = get_tools_for_level(level)

    # TESTS_ONLY: return immediately with pass, no signal, no tools called
    if level == VerificationLevel.TESTS_ONLY:
        return {
            "overall_status": "pass",
            "verification_level": str(level),
            "results": [],
            "signal_recorded": False,
        }

    # Get the dispatch map (lazily populated)
    dispatch = _get_tool_dispatch()

    # Call each tool for this level and collect results
    results = []
    for tool_name in tool_names:
        tool_fn = dispatch[tool_name]

        # Call each tool with the appropriate arguments based on its signature
        if tool_name == "prusti":
            result = await tool_fn(
                session_id=session_id,
                source_file=source_file,
                project_dir=project_dir,
            )
        elif tool_name == "kani":
            result = await tool_fn(
                session_id=session_id,
                source_file=source_file,
                harness_name=harness_name,
                project_dir=project_dir,
            )
        elif tool_name == "semver":
            result = await tool_fn(
                session_id=session_id,
                project_dir=project_dir,
                baseline_rev=baseline_rev,
            )
        elif tool_name == "crosshair":
            result = await tool_fn(
                session_id=session_id,
                source_file=source_file,
            )
        elif tool_name == "composability":
            result = await tool_fn(
                session_id=session_id,
                postconditions=postconditions or [],
                preconditions=preconditions or [],
                variables=variables or {},
            )
        else:
            # Fallback for unknown tools
            result = await tool_fn(session_id=session_id, project_dir=project_dir)

        results.append(result)

    # Aggregate results: all pass -> pass, any fail -> fail, error with no fail -> error
    statuses = [r.get("status", "error") for r in results]
    has_fail = any(s == "fail" for s in statuses)
    has_error = any(s == "error" for s in statuses)

    if has_fail:
        overall_status = "fail"
    elif has_error:
        overall_status = "error"
    else:
        overall_status = "pass"

    # Record signal based on overall status
    signal_recorded = False
    if overall_status == "pass":
        record_agent_signal(
            signal_type="VERIFICATION_PASS",
            session_id=session_id,
            context={"verification_level": str(level)},
        )
        signal_recorded = True
    elif overall_status == "fail":
        # Find the first failing tool and build context
        fail_result = None
        fail_tool_name = None
        for i, result in enumerate(results):
            if result.get("status") == "fail":
                fail_result = result
                fail_tool_name = tool_names[i]
                break

        fail_context = _build_fail_context(fail_tool_name, fail_result)
        record_agent_signal(
            signal_type="VERIFICATION_FAIL",
            session_id=session_id,
            context=fail_context,
        )
        signal_recorded = True
    # For 'error' status: do not record any signal

    return {
        "overall_status": overall_status,
        "verification_level": str(level),
        "results": results,
        "signal_recorded": signal_recorded,
    }


def register_tools(mcp, db: DatabaseManager) -> None:
    """Register verification orchestrator tools with FastMCP server."""
    global _db
    _db = db
    mcp.tool()(run_verification)
    logger.info(
        "Verification orchestrator tools registered",
        extra={'tool_name': 'verification_orchestrator'},
    )
