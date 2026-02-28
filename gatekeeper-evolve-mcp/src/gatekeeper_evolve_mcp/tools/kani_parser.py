"""
Parser for Kani verification tool stdout output.

Extracts structured check results, overall verification status, and
counterexample traces from the output that 'cargo kani' produces on stdout.

This is a pure parsing module with no external dependencies.
It is imported by kani.py to parse subprocess output.

Usage:
    from gatekeeper_mcp.tools.kani_parser import (
        parse_kani_results,
        parse_kani_verification_status,
        parse_kani_counterexamples,
    )

    checks = parse_kani_results(stdout_text)
    # [{'check_name': 'harness.assertion.1', 'status': 'SUCCESS', 'message': 'bounds check'}, ...]

    overall = parse_kani_verification_status(stdout_text)
    # 'SUCCESSFUL' or 'FAILED' or None

    counterexamples = parse_kani_counterexamples(stdout_text)
    # [{'harness': 'my_harness', 'variables': {'x': '-2147483648i32', 'y': '1i32'}}, ...]
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# --- Regex patterns for Kani stdout ---

# Bracket format: [check_name] Status: SUCCESS/FAILURE/UNREACHABLE
BRACKET_CHECK_PATTERN = re.compile(
    r'\[(.+?)\]\s+Status:\s+(SUCCESS|FAILURE|UNREACHABLE)'
)

# Named format: Check N: check_name
NAMED_CHECK_HEADER_PATTERN = re.compile(
    r'Check\s+\d+:\s+(.+?)\s*$'
)

# Status line (for named format): - Status: SUCCESS/FAILURE/UNREACHABLE
STATUS_LINE_PATTERN = re.compile(
    r'\s*-\s*Status:\s+(SUCCESS|FAILURE|UNREACHABLE)'
)

# Description line: Description: "message" or Description: message
DESCRIPTION_PATTERN = re.compile(
    r'\s*(?:-\s*)?Description:\s*"?([^"]*?)"?\s*$'
)

# Overall verification status: VERIFICATION:- SUCCESSFUL or VERIFICATION:- FAILED
VERIFICATION_STATUS_PATTERN = re.compile(
    r'VERIFICATION:-\s+(SUCCESSFUL|FAILED)'
)

# Concrete playback header
CONCRETE_PLAYBACK_HEADER = re.compile(
    r'Concrete playback unit test for\s+(.+?):'
)

# Variable assignment in concrete playback: let var_name: type = value;
CONCRETE_PLAYBACK_VAR = re.compile(
    r'let\s+(\w+):\s+\w+\s*=\s*(.+?);'
)


def parse_kani_results(stdout: str) -> list[dict]:
    """
    Parse Kani stdout for per-check results from the RESULTS section.

    Handles two output formats:
    1. Bracket format: [check_name] Status: SUCCESS
    2. Named format: Check N: check_name / - Status: SUCCESS

    Each check becomes a dict with keys:
    - check_name: str (the full check identifier, e.g., 'harness.assertion.1')
    - status: str ('SUCCESS', 'FAILURE', or 'UNREACHABLE')
    - message: str (description text, or empty string if no description)

    Args:
        stdout: The stdout output from cargo kani

    Returns:
        List of check dicts. Empty list if no results found.
    """
    if not stdout or not stdout.strip():
        return []

    checks = []
    lines = stdout.split('\n')

    # Try bracket format first (more specific)
    for i, line in enumerate(lines):
        bracket_match = BRACKET_CHECK_PATTERN.search(line)
        if bracket_match:
            check_name = bracket_match.group(1).strip()
            status = bracket_match.group(2)
            message = ''

            # Look ahead for Description line
            for j in range(i + 1, min(i + 3, len(lines))):
                desc_match = DESCRIPTION_PATTERN.search(lines[j])
                if desc_match:
                    message = desc_match.group(1).strip()
                    break
                # Stop if we hit another check line or empty significant delimiter
                if BRACKET_CHECK_PATTERN.search(lines[j]):
                    break

            checks.append({
                'check_name': check_name,
                'status': status,
                'message': message,
            })

    # If bracket format found results, return them
    if checks:
        logger.debug(f"Parsed {len(checks)} checks from Kani stdout (bracket format)")
        return checks

    # Try named format: Check N: name + - Status: STATUS
    i = 0
    while i < len(lines):
        header_match = NAMED_CHECK_HEADER_PATTERN.search(lines[i])
        if header_match:
            check_name = header_match.group(1).strip()
            status = ''
            message = ''

            # Look ahead for Status and Description lines
            for j in range(i + 1, min(i + 5, len(lines))):
                status_match = STATUS_LINE_PATTERN.search(lines[j])
                if status_match:
                    status = status_match.group(1)
                desc_match = DESCRIPTION_PATTERN.search(lines[j])
                if desc_match and not STATUS_LINE_PATTERN.search(lines[j]):
                    message = desc_match.group(1).strip()

            if status:  # Only add if we found a valid status
                checks.append({
                    'check_name': check_name,
                    'status': status,
                    'message': message,
                })
        i += 1

    logger.debug(f"Parsed {len(checks)} checks from Kani stdout (named format)")
    return checks


def parse_kani_verification_status(stdout: str) -> Optional[str]:
    """
    Parse Kani stdout for the overall verification status.

    Looks for the 'VERIFICATION:- SUCCESSFUL' or 'VERIFICATION:- FAILED' line.

    Args:
        stdout: The stdout output from cargo kani

    Returns:
        'SUCCESSFUL' or 'FAILED' if found, None if no verification status line present.
    """
    if not stdout or not stdout.strip():
        return None

    match = VERIFICATION_STATUS_PATTERN.search(stdout)
    if match:
        return match.group(1)

    return None


def parse_kani_counterexamples(stdout: str) -> list[dict]:
    """
    Parse Kani stdout for concrete playback traces.

    These appear when --concrete-playback=print is passed and look like:

        Concrete playback unit test for my_harness:
        ```rust
        #[test]
        fn kani_concrete_playback_my_harness() {
            let x: i32 = -2147483648i32;
            let y: i32 = 1i32;
        }
        ```

    Each counterexample becomes a dict with keys:
    - harness: str (the harness name)
    - variables: dict (variable name -> value string mappings)

    Args:
        stdout: The stdout output from cargo kani --concrete-playback=print

    Returns:
        List of counterexample dicts. Empty list if no concrete playback traces found.
    """
    if not stdout or not stdout.strip():
        return []

    counterexamples = []
    lines = stdout.split('\n')

    i = 0
    while i < len(lines):
        header_match = CONCRETE_PLAYBACK_HEADER.search(lines[i])
        if header_match:
            harness_name = header_match.group(1).strip()
            variables = {}

            # Scan subsequent lines for variable assignments
            j = i + 1
            while j < len(lines):
                var_match = CONCRETE_PLAYBACK_VAR.search(lines[j])
                if var_match:
                    var_name = var_match.group(1)
                    var_value = var_match.group(2).strip()
                    variables[var_name] = var_value
                    j += 1
                elif '```' in lines[j] and j > i + 1 and variables:
                    # End of code block
                    break
                elif lines[j].strip() == '' and variables:
                    # Empty line after variables could be end of block
                    j += 1
                else:
                    j += 1

                # Safety: don't scan more than 30 lines for one counterexample
                if j - i > 30:
                    break

            counterexamples.append({
                'harness': harness_name,
                'variables': variables,
            })

            i = j
        else:
            i += 1

    logger.debug(f"Parsed {len(counterexamples)} counterexamples from Kani stdout")
    return counterexamples
