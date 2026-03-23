"""
Token and session validation utilities for Gatekeeper MCP.

Provides validation functions for:
- Token format validation (GK_COMPLETE_*, TQG_PASS_*)
- Session ID format validation
- Token type extraction

Token formats:
    GK_COMPLETE_[a-f0-9]{32} - Gatekeeper verification token
    TQG_PASS_[a-f0-9]{32} - Test quality gate token

Session ID format:
    gk_YYYYMMDD_[a-f0-9]{6} - Session identifier
"""

import re
from typing import Optional


class ValidationError(ValueError):
    """Raised when validation fails."""
    pass


# Token format patterns
TOKEN_PATTERN = re.compile(r'^(GK_COMPLETE|TQG_PASS|TPG_COMPLETE)_[a-f0-9]{32}$')
SESSION_ID_PATTERN = re.compile(r'^gk_\d{8}_[a-f0-9]{6}$')


def validate_token_format(token: str) -> str:
    """
    Validate token format and return token type.

    Args:
        token: Token string to validate (e.g., "GK_COMPLETE_abc...123")

    Returns:
        str: Token type ("GK_COMPLETE" or "TQG_PASS")

    Raises:
        ValidationError: If token format is invalid

    Examples:
        >>> validate_token_format("GK_COMPLETE_" + "a" * 32)
        'GK_COMPLETE'
        >>> validate_token_format("TQG_PASS_" + "b" * 32)
        'TQG_PASS'
        >>> validate_token_format("invalid_token")
        ValidationError: Invalid token format...
    """
    if not token:
        raise ValidationError("Token cannot be empty")

    match = TOKEN_PATTERN.match(token)
    if not match:
        raise ValidationError(
            f"Invalid token format. Expected GK_COMPLETE_[32hex] or TQG_PASS_[32hex], "
            f"got: {token[:20]}... (token must have 32 lowercase hex characters after prefix)"
        )

    return match.group(1)


def validate_session_id(session_id: str) -> bool:
    """
    Validate session ID format.

    Args:
        session_id: Session identifier to validate (e.g., "gk_20260223_a3f2c1")

    Returns:
        bool: True if session ID format is valid

    Raises:
        ValidationError: If session ID format is invalid

    Examples:
        >>> validate_session_id("gk_20260223_a3f2c1")
        True
        >>> validate_session_id("invalid_session")
        ValidationError: Invalid session ID format...
    """
    if not session_id:
        raise ValidationError("Session ID cannot be empty")

    if not SESSION_ID_PATTERN.match(session_id):
        raise ValidationError(
            f"Invalid session ID format. Expected gk_YYYYMMDD_[6hex], "
            f"got: {session_id} (format: gk_TIMESTAMP_RANDOMHEX)"
        )

    return True


def token_type_from_string(token: str) -> Optional[str]:
    """
    Extract token type from token string without full validation.

    This is a helper function that extracts the token type prefix
    without performing full format validation. Useful for quick checks.

    Args:
        token: Token string to extract type from

    Returns:
        Optional[str]: Token type ("GK_COMPLETE", "TQG_PASS") or None if not recognized

    Examples:
        >>> token_type_from_string("GK_COMPLETE_abc...")
        'GK_COMPLETE'
        >>> token_type_from_string("unknown_token")
        None
    """
    if token.startswith("GK_COMPLETE_"):
        return "GK_COMPLETE"
    elif token.startswith("TQG_PASS_"):
        return "TQG_PASS"
    elif token.startswith("TPG_COMPLETE_"):
        return "TPG_COMPLETE"
    return None


def is_valid_hex_string(s: str, length: int) -> bool:
    """
    Check if string is a valid hex string of specified length.

    Args:
        s: String to check
        length: Expected length

    Returns:
        bool: True if string is valid hex of specified length

    Examples:
        >>> is_valid_hex_string("a" * 32, 32)
        True
        >>> is_valid_hex_string("ABC" * 11, 32)
        False  # uppercase not allowed
    """
    if len(s) != length:
        return False
    if length == 0:
        return True  # Empty string is valid when length is 0
    return bool(re.match(r'^[a-f0-9]+$', s))
