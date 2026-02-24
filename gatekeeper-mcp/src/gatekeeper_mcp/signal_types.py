"""
Signal type definitions for Gatekeeper agent outputs.

This module defines the SignalType enum for all agent-emitted signals
used in the Gatekeeper verification workflow.

Signal types represent discrete events that agents emit to communicate
their progress to the orchestrator:
- TESTS_WRITTEN: Tester agent finished writing tests
- VERIFICATION_PASS/FAIL: Verifier approved/rejected implementation
- ASSESSMENT_PASS/FAIL: Test assessor approved/rejected test quality
- IMPLEMENTATION_READY: Executor ready for verification
- PHASE_ASSESSMENT_PASS: Phase-level test assessment passed
- PHASE_VERIFICATION_PASS: Phase-level verification passed
"""

from enum import Enum
from typing import Dict


class SignalType(str, Enum):
    """
    Enumeration of all agent signal types.

    Signal types are string enum values that represent discrete events
    in the Gatekeeper verification workflow.

    Usage:
        signal_type = SignalType.TESTS_WRITTEN
        print(signal_type.value)  # "TESTS_WRITTEN"

        # Validate from string
        validated = validate_signal_type("TESTS_WRITTEN")
    """

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
    """
    Validate and convert a string to a SignalType enum.

    Args:
        signal_type: String representation of signal type

    Returns:
        SignalType: Validated signal type enum

    Raises:
        ValueError: If signal_type is not a valid SignalType
        TypeError: If signal_type is not a string

    Example:
        >>> validate_signal_type("TESTS_WRITTEN")
        <SignalType.TESTS_WRITTEN: 'TESTS_WRITTEN'>

        >>> validate_signal_type("invalid")
        ValueError: Invalid signal type 'invalid'. Valid types: TESTS_WRITTEN, ...
    """
    if not isinstance(signal_type, str):
        raise TypeError(
            f"signal_type must be a string, got {type(signal_type).__name__}"
        )
    try:
        return SignalType(signal_type.upper())
    except ValueError:
        valid_types = ", ".join([s.value for s in SignalType])
        raise ValueError(
            f"Invalid signal type '{signal_type}'. Valid types: {valid_types}"
        )


def is_completion_signal(signal_type: SignalType) -> bool:
    """
    Check if a signal type indicates successful completion.

    Completion signals are those that indicate a workflow step
    has completed successfully and can trigger state transitions.

    Args:
        signal_type: SignalType enum value

    Returns:
        bool: True if signal indicates completion, False otherwise

    Example:
        >>> is_completion_signal(SignalType.VERIFICATION_PASS)
        True
        >>> is_completion_signal(SignalType.VERIFICATION_FAIL)
        False
    """
    return signal_type in COMPLETION_SIGNALS


def get_all_signal_types() -> list[SignalType]:
    """
    Get a list of all valid signal types.

    Returns:
        List of all SignalType enum values

    Example:
        >>> get_all_signal_types()
        [<SignalType.TESTS_WRITTEN: 'TESTS_WRITTEN'>, ...]
    """
    return list(SignalType)
