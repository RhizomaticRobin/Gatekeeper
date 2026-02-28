"""
Parser for Prusti verification tool stderr output.

Extracts structured error information and counterexamples from the
rustc-style error format that Prusti produces on stderr.

This is a pure parsing module with no external dependencies.
It is imported by prusti.py to parse subprocess output.

Usage:
    from gatekeeper_mcp.tools.prusti_parser import (
        parse_prusti_errors,
        parse_prusti_counterexamples,
    )

    errors = parse_prusti_errors(stderr_text)
    # [{'code': 'E0001', 'message': '...', 'file': '...', 'line': 42, 'col': 5}, ...]

    counterexamples = parse_prusti_counterexamples(stderr_text)
    # [{'function': 'my_fn', 'values': {'x': '0', 'y': '-1'}}, ...]
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Regex patterns for Prusti/rustc error format
# Matches: error[E0001]: some error message
ERROR_PATTERN = re.compile(r'error\[E(\d+)\]:\s*(.+)')

# Matches:  --> path/to/file.rs:42:5
LOCATION_PATTERN = re.compile(r'\s*-->\s*(.+):(\d+):(\d+)')

# Matches: counterexample for "function_name"
COUNTEREXAMPLE_HEADER_PATTERN = re.compile(r'counterexample for "([^"]+)"')

# Matches:   variable_name = value
COUNTEREXAMPLE_VALUE_PATTERN = re.compile(r'\s+(\w+)\s*=\s*(.+)')


def parse_prusti_errors(stderr: str) -> list[dict]:
    """
    Parse Prusti stderr for error[E...] lines with file:line:col locations.

    Each error becomes a dict with keys:
    - code: str (e.g., 'E0001')
    - message: str (the error message text)
    - file: str or None (source file path, if location line follows)
    - line: int or None (line number, if location line follows)
    - col: int or None (column number, if location line follows)

    Args:
        stderr: The stderr output from cargo prusti

    Returns:
        List of error dicts. Empty list if no errors found.
    """
    if not stderr or not stderr.strip():
        return []

    errors = []
    lines = stderr.split('\n')

    i = 0
    while i < len(lines):
        error_match = ERROR_PATTERN.search(lines[i])
        if error_match:
            code = f"E{error_match.group(1)}"
            message = error_match.group(2).strip()

            # Look ahead for location line
            file_path: Optional[str] = None
            line_num: Optional[int] = None
            col_num: Optional[int] = None

            # Check next few lines for a location marker
            for j in range(i + 1, min(i + 4, len(lines))):
                loc_match = LOCATION_PATTERN.search(lines[j])
                if loc_match:
                    file_path = loc_match.group(1).strip()
                    line_num = int(loc_match.group(2))
                    col_num = int(loc_match.group(3))
                    break

            errors.append({
                'code': code,
                'message': message,
                'file': file_path,
                'line': line_num,
                'col': col_num,
            })

        i += 1

    logger.debug(f"Parsed {len(errors)} errors from Prusti stderr")
    return errors


def parse_prusti_counterexamples(stderr: str) -> list[dict]:
    """
    Parse Prusti stderr for counterexample blocks.

    Counterexamples appear when PRUSTI_COUNTEREXAMPLE=true and look like:

        counterexample for "function_name"
          x = 0
          y = -1

    Each counterexample becomes a dict with keys:
    - function: str (the function name)
    - values: dict (variable name -> value string mappings)

    Args:
        stderr: The stderr output from cargo prusti

    Returns:
        List of counterexample dicts. Empty list if no counterexamples found.
    """
    if not stderr or not stderr.strip():
        return []

    counterexamples = []
    lines = stderr.split('\n')

    i = 0
    while i < len(lines):
        header_match = COUNTEREXAMPLE_HEADER_PATTERN.search(lines[i])
        if header_match:
            fn_name = header_match.group(1)
            values = {}

            # Collect variable assignments following the header
            j = i + 1
            while j < len(lines):
                val_match = COUNTEREXAMPLE_VALUE_PATTERN.match(lines[j])
                if val_match:
                    var_name = val_match.group(1)
                    var_value = val_match.group(2).strip()
                    values[var_name] = var_value
                    j += 1
                elif lines[j].strip() == '':
                    # Empty line may be part of block, skip
                    j += 1
                else:
                    # Non-matching line means end of this counterexample block
                    break

            counterexamples.append({
                'function': fn_name,
                'values': values,
            })

            i = j
        else:
            i += 1

    logger.debug(f"Parsed {len(counterexamples)} counterexamples from Prusti stderr")
    return counterexamples
