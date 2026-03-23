"""
Token and session validation utilities for Gatekeeper Evolve MCP.

Provides validation functions for:
- Token format validation (GK_COMPLETE_*, TQG_PASS_*)
- Session ID format validation
- Token type extraction
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
    """Validate token format and return token type."""
    if not token:
        raise ValidationError("Token cannot be empty")

    token_type = token_type_from_string(token)
    if token_type is None:
        raise ValidationError(
            f"Invalid token format. Expected GK_COMPLETE_[32hex] or TQG_PASS_[32hex], "
            f"got: {token[:20]}... (unrecognized token prefix)"
        )

    hex_portion = token[len(token_type) + 1:]
    if not is_valid_hex_string(hex_portion, 32):
        raise ValidationError(
            f"Invalid token format. Expected GK_COMPLETE_[32hex] or TQG_PASS_[32hex], "
            f"got: {token[:20]}... (token must have 32 lowercase hex characters after prefix)"
        )

    return token_type


def validate_session_id(session_id: str) -> bool:
    """Validate session ID format."""
    if not session_id:
        raise ValidationError("Session ID cannot be empty")

    if not SESSION_ID_PATTERN.match(session_id):
        raise ValidationError(
            f"Invalid session ID format. Expected gk_YYYYMMDD_[6hex], "
            f"got: {session_id} (format: gk_TIMESTAMP_RANDOMHEX)"
        )

    return True


def token_type_from_string(token: str) -> Optional[str]:
    """Extract token type from token string without full validation."""
    if token.startswith("GK_COMPLETE_"):
        return "GK_COMPLETE"
    elif token.startswith("TQG_PASS_"):
        return "TQG_PASS"
    elif token.startswith("TPG_COMPLETE_"):
        return "TPG_COMPLETE"
    return None


def is_valid_hex_string(s: str, length: int) -> bool:
    """Check if string is a valid hex string of specified length."""
    if len(s) != length:
        return False
    if length == 0:
        return True
    return bool(re.match(r'^[a-f0-9]+$', s))
