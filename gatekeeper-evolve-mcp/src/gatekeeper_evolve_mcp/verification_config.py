"""Verification level configuration and dispatch mapping for ERMACK v2."""
from enum import Enum


class VerificationLevel(str, Enum):
    """Verification levels controlling which formal verification tools run."""
    TESTS_ONLY = "tests_only"
    PRUSTI = "prusti"
    KANI = "kani"
    CROSSHAIR = "crosshair"
    FULL = "full"
    FULL_PYTHON = "full_python"

    def __str__(self) -> str:
        return self.value

    def __format__(self, format_spec: str) -> str:
        return format(self.value, format_spec)


LEVEL_TOOL_DISPATCH: dict[VerificationLevel, list[str]] = {
    VerificationLevel.TESTS_ONLY: [],
    VerificationLevel.PRUSTI: ["prusti"],
    VerificationLevel.KANI: ["kani"],
    VerificationLevel.CROSSHAIR: ["crosshair"],
    VerificationLevel.FULL: ["prusti", "kani", "semver"],
    VerificationLevel.FULL_PYTHON: ["crosshair", "composability"],
}


def get_tools_for_level(level: VerificationLevel) -> list[str]:
    """Return list of tool names to dispatch for the given verification level."""
    return list(LEVEL_TOOL_DISPATCH[level])


def parse_verification_level(level_str: str) -> VerificationLevel:
    """Parse a string into a VerificationLevel enum value (case-insensitive).

    Raises ValueError with helpful message listing valid values on invalid input.
    """
    normalized = level_str.strip().lower()
    for member in VerificationLevel:
        if member.value == normalized:
            return member
    valid = ", ".join(m.value for m in VerificationLevel)
    raise ValueError(f"Invalid verification level: '{level_str}'. Valid values: {valid}")
