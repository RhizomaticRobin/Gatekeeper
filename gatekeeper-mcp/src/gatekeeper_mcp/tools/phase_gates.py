"""
Phase gate MCP tools for Gatekeeper server.

Provides tools for:
- submit_pvg_token: Submit phase verification gate tokens
- check_phase_integration: Verify phase integration requirements
"""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from fastmcp import FastMCP
from gatekeeper_mcp.models import PhaseToken
from gatekeeper_mcp.database import DatabaseManager

if TYPE_CHECKING:
    from gatekeeper_mcp.state_writer import StateWriter

logger = logging.getLogger(__name__)

# Database manager and state writer will be injected from server_v3
_db: Optional[DatabaseManager] = None
_state_writer: Optional["StateWriter"] = None

# PVG token pattern: PVG_COMPLETE_ followed by exactly 32 lowercase hex characters
PVG_TOKEN_PATTERN = re.compile(r'^PVG_COMPLETE_[a-f0-9]{32}$')


def register_tools(mcp: FastMCP, db: DatabaseManager, state_writer: Optional["StateWriter"] = None) -> None:
    """
    Register phase gate tools with FastMCP server.

    Args:
        mcp: FastMCP server instance
        db: DatabaseManager instance from server
        state_writer: StateWriter instance from server (optional)
    """
    global _db, _state_writer
    _db = db
    _state_writer = state_writer

    # Register tools
    mcp.tool()(submit_pvg_token)
    mcp.tool()(check_phase_integration)

    logger.info("Phase gate tools registered", extra={'tool_name': 'phase_gates'})


def submit_pvg_token(
    session_id: str,
    token_value: str,
    phase_id: int,
    integration_check_passed: bool
) -> Dict[str, Any]:
    """
    Submit a phase verification gate token.

    Args:
        session_id: Session ID to associate token with
        token_value: PVG token (format: PVG_COMPLETE_[32 hex chars])
        phase_id: Phase number this token represents
        integration_check_passed: Whether integration check passed

    Returns:
        Dict containing PhaseToken dataclass fields

    Raises:
        ValueError: If token format is invalid
        ValueError: If token already exists

    Example:
        token = submit_pvg_token(
            session_id="gk_20260223_a3f2c1",
            token_value="PVG_COMPLETE_abc123...",
            phase_id=6,
            integration_check_passed=True
        )
    """
    logger.info("Submitting PVG token", extra={
        'tool_name': 'submit_pvg_token',
        'session_id': session_id,
        'phase_id': phase_id
    })

    # Validate token format
    if not PVG_TOKEN_PATTERN.match(token_value):
        logger.error(f"Invalid PVG token format: {token_value}", extra={'tool_name': 'submit_pvg_token'})
        raise ValueError(f"Invalid PVG token format: {token_value}. Expected format: PVG_COMPLETE_[32 lowercase hex chars]")

    # Check for duplicate token
    existing = _db.fetchone('SELECT id FROM phase_tokens WHERE token_value = ?', (token_value,))
    if existing:
        logger.error(f"PVG token already exists: {token_value}", extra={'tool_name': 'submit_pvg_token'})
        raise ValueError(f"PVG token already exists: {token_value}")

    # Create token data
    created_at = datetime.now(timezone.utc).isoformat()
    token_data = {
        'session_id': session_id,
        'token_value': token_value,
        'phase_id': phase_id,
        'integration_check_passed': 1 if integration_check_passed else 0,
        'created_at': created_at,
        'validated': 0
    }

    # Insert into database
    _db.insert('phase_tokens', token_data)

    # Retrieve created token
    row = _db.fetchone('SELECT * FROM phase_tokens WHERE token_value = ?', (token_value,))
    phase_token = PhaseToken.from_row(row)

    # Write state files
    if _state_writer:
        try:
            _state_writer.write_state_files(session_id)
            logger.debug(
                "State files written after phase token submission",
                extra={'tool_name': 'submit_pvg_token', 'session_id': session_id}
            )
        except Exception as e:
            logger.error(
                f"Failed to write state files: {e}",
                extra={'tool_name': 'submit_pvg_token', 'session_id': session_id}
            )

    logger.info("PVG token submitted successfully", extra={
        'tool_name': 'submit_pvg_token',
        'session_id': session_id,
        'phase_id': phase_id,
        'token_value': token_value
    })

    return phase_token.to_dict()


def check_phase_integration(
    phase_id: int,
    required_artifacts: List[str],
    project_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check phase integration requirements by verifying artifacts exist.

    Args:
        phase_id: Phase number to check
        required_artifacts: List of artifact file paths to verify
        project_dir: Optional project directory for resolving relative paths

    Returns:
        Dict with:
        - status: "PASS" or "NEEDS_FIXES"
        - phase_id: Phase number checked
        - missing_artifacts: List of missing artifact paths
        - details: Array of artifact check details
        - prior_phase_status: Status of prior phase (if applicable)
        - checked_at: ISO 8601 timestamp

    Example:
        result = check_phase_integration(
            phase_id=6,
            required_artifacts=["phase-5.yaml", "task-5.1.md"],
            project_dir="/workspace/craftium"
        )
        # Returns: {"status": "PASS", "missing_artifacts": [], ...}
    """
    logger.info("Checking phase integration", extra={
        'tool_name': 'check_phase_integration',
        'phase_id': phase_id,
        'artifact_count': len(required_artifacts)
    })

    checked_at = datetime.now(timezone.utc).isoformat()
    missing_artifacts = []
    details = []

    # Check each artifact
    for artifact in required_artifacts:
        # Resolve full path
        if project_dir and not os.path.isabs(artifact):
            full_path = os.path.join(project_dir, artifact)
        else:
            full_path = artifact

        exists = os.path.isfile(full_path)
        details.append({
            'artifact': artifact,
            'full_path': full_path,
            'exists': exists
        })

        if not exists:
            missing_artifacts.append(artifact)

    # Determine status
    status = 'PASS' if len(missing_artifacts) == 0 else 'NEEDS_FIXES'

    # Check prior phase status (phase 1 has no prior)
    prior_phase_status = None
    if phase_id > 1:
        prior_phase_id = phase_id - 1
        prior_row = _db.fetchone(
            'SELECT * FROM phase_tokens WHERE phase_id = ? ORDER BY created_at DESC LIMIT 1',
            (prior_phase_id,)
        )

        if prior_row:
            prior_token = PhaseToken.from_row(prior_row)
            prior_phase_status = {
                'phase_id': prior_phase_id,
                'completed': True,
                'integration_check_passed': prior_token.integration_check_passed,
                'completed_at': prior_token.created_at
            }
        else:
            prior_phase_status = {
                'phase_id': prior_phase_id,
                'completed': False,
                'integration_check_passed': False,
                'completed_at': None
            }

    result = {
        'status': status,
        'phase_id': phase_id,
        'missing_artifacts': missing_artifacts,
        'details': details,
        'prior_phase_status': prior_phase_status,
        'checked_at': checked_at
    }

    logger.info("Phase integration check complete", extra={
        'tool_name': 'check_phase_integration',
        'phase_id': phase_id,
        'status': status,
        'missing_count': len(missing_artifacts)
    })

    return result
