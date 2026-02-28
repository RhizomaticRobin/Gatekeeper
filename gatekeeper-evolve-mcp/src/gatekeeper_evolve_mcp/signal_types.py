"""
Signal type definitions for Gatekeeper agent outputs.

This module defines the SignalType enum for all agent-emitted signals
used in the Gatekeeper verification workflow.
"""

from enum import Enum
from typing import Dict


class SignalType(str, Enum):
    """Enumeration of all agent signal types."""

    # Testing phase signals
    TESTS_WRITTEN = "TESTS_WRITTEN"
    ASSESSMENT_PASS = "ASSESSMENT_PASS"
    ASSESSMENT_FAIL = "ASSESSMENT_FAIL"

    # Implementation phase signals
    IMPLEMENTATION_READY = "IMPLEMENTATION_READY"
    VERIFICATION_PASS = "VERIFICATION_PASS"
    VERIFICATION_FAIL = "VERIFICATION_FAIL"

    # Phase-level signals
    PHASE_ASSESSMENT_PASS = "PHASE_ASSESSMENT_PASS"
    PHASE_VERIFICATION_PASS = "PHASE_VERIFICATION_PASS"


# Human-readable descriptions for each signal type
SIGNAL_TYPE_DESCRIPTIONS: Dict[SignalType, str] = {
    SignalType.TESTS_WRITTEN: "Tester agent has finished writing tests",
    SignalType.ASSESSMENT_PASS: "Test assessor has approved test quality",
    SignalType.ASSESSMENT_FAIL: "Test assessor has rejected test quality",
    SignalType.IMPLEMENTATION_READY: "Executor is ready for verification",
    SignalType.VERIFICATION_PASS: "Verifier has approved implementation",
    SignalType.VERIFICATION_FAIL: "Verifier has rejected implementation",
    SignalType.PHASE_ASSESSMENT_PASS: "Phase-level test assessment has passed",
    SignalType.PHASE_VERIFICATION_PASS: "Phase-level verification has passed",
}

# Signals that indicate successful completion (used for workflow transitions)
COMPLETION_SIGNALS = {
    SignalType.VERIFICATION_PASS,
    SignalType.ASSESSMENT_PASS,
    SignalType.PHASE_ASSESSMENT_PASS,
    SignalType.PHASE_VERIFICATION_PASS,
}


def validate_signal_type(signal_type: str) -> SignalType:
    """Validate and convert a string to a SignalType enum."""
    if not isinstance(signal_type, str):
        raise TypeError(
            f"signal_type must be a string, got {type(signal_type).__name__}"
        )
    try:
        return SignalType(signal_type.upper())
    except ValueError:
        all_types = get_all_signal_types()
        type_lines = "\n".join(
            f"  - {t.value}: {SIGNAL_TYPE_DESCRIPTIONS.get(t, 'No description')}"
            for t in all_types
        )
        raise ValueError(
            f"Invalid signal type '{signal_type}'. Valid types:\n{type_lines}"
        )


def is_completion_signal(signal_type: SignalType) -> bool:
    """Check if a signal type indicates successful completion."""
    return signal_type in COMPLETION_SIGNALS


def get_all_signal_types() -> list[SignalType]:
    """Get a list of all valid signal types."""
    return list(SignalType)
