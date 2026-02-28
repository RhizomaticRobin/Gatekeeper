"""
Parser for CrossHair verification tool output and icontract decorator detection.

Extracts structured error information from CrossHair's mypy-format output
and checks Python source files for icontract decorator presence.

This is a pure parsing module with no external dependencies (no MCP, no DB, no subprocess).
It is imported by python_contracts.py to parse output and validate source files.

Usage:
    from gatekeeper_mcp.tools.python_contracts_parser import (
        parse_crosshair_output,
        check_icontract_decorators,
    )

    errors = parse_crosshair_output(stdout_text)
    # [{'file': 'file.py', 'line': 10, 'error_type': 'error', 'message': 'counterexample: x=-1'}, ...]

    decorators = check_icontract_decorators(source_text)
    # {'has_require': True, 'has_ensure': True, 'decorator_count': 3}
"""

import re
import logging

logger = logging.getLogger(__name__)


# Regex patterns for CrossHair mypy-format output
# Matches: /path/to/file.py:10: error: counterexample message
# Also matches: file.py:10: error: message
CROSSHAIR_ERROR_PATTERN = re.compile(
    r'^(.+?):(\d+):\s*(error|warning):\s*(.+)$',
    re.MULTILINE,
)

# Regex patterns for icontract decorator detection
# Matches: @icontract.require(...) and @icontract.ensure(...)
ICONTRACT_DOTTED_PATTERN = re.compile(
    r'@icontract\.(require|ensure)\s*\(',
)

# Matches: @require(...) and @ensure(...) (after from icontract import ...)
ICONTRACT_DIRECT_PATTERN = re.compile(
    r'@(require|ensure)\s*\(',
)

# Matches: from icontract import ... (to validate that @require/@ensure are from icontract)
ICONTRACT_IMPORT_PATTERN = re.compile(
    r'from\s+icontract\s+import\s+',
)

# Matches: import icontract
ICONTRACT_MODULE_IMPORT_PATTERN = re.compile(
    r'import\s+icontract',
)


def parse_crosshair_output(stdout: str) -> list[dict]:
    """
    Parse CrossHair stdout for mypy-format error/warning lines.

    Each error line becomes a dict with keys:
    - file: str (source file path)
    - line: int (line number)
    - error_type: str ('error' or 'warning')
    - message: str (the error/counterexample message)

    Args:
        stdout: The stdout output from crosshair check

    Returns:
        List of error dicts. Empty list if no errors found.
    """
    if not stdout or not stdout.strip():
        return []

    errors = []
    for match in CROSSHAIR_ERROR_PATTERN.finditer(stdout):
        errors.append({
            'file': match.group(1).strip(),
            'line': int(match.group(2)),
            'error_type': match.group(3),
            'message': match.group(4).strip(),
        })

    logger.debug(f"Parsed {len(errors)} errors from CrossHair output")
    return errors


def check_icontract_decorators(source_text: str) -> dict:
    """
    Check a Python source file for icontract decorator presence.

    Detects both forms:
    1. @icontract.require(...) / @icontract.ensure(...) -- with module-qualified name
    2. @require(...) / @ensure(...) -- when imported via 'from icontract import require, ensure'

    For the direct form (@require/@ensure), also checks that an icontract import exists
    to distinguish from other libraries that might use the same decorator names.

    Args:
        source_text: The full text content of a Python source file

    Returns:
        Dict with keys:
        - has_require: bool -- True if any @require or @icontract.require found
        - has_ensure: bool -- True if any @ensure or @icontract.ensure found
        - decorator_count: int -- total number of icontract decorators found
    """
    if not source_text or not source_text.strip():
        return {
            'has_require': False,
            'has_ensure': False,
            'decorator_count': 0,
        }

    # Remove comments from source to avoid false positives
    source_without_comments = _remove_comments(source_text)

    # Check for icontract imports
    has_icontract_import = bool(
        ICONTRACT_IMPORT_PATTERN.search(source_without_comments) or
        ICONTRACT_MODULE_IMPORT_PATTERN.search(source_without_comments)
    )

    # Find dotted form: @icontract.require/@icontract.ensure
    dotted_matches = ICONTRACT_DOTTED_PATTERN.findall(source_without_comments)
    dotted_requires = sum(1 for m in dotted_matches if m == 'require')
    dotted_ensures = sum(1 for m in dotted_matches if m == 'ensure')

    # Find direct form: @require/@ensure (only count if icontract is imported)
    direct_requires = 0
    direct_ensures = 0
    if has_icontract_import:
        direct_matches = ICONTRACT_DIRECT_PATTERN.findall(source_without_comments)
        direct_requires = sum(1 for m in direct_matches if m == 'require')
        direct_ensures = sum(1 for m in direct_matches if m == 'ensure')

    total_requires = dotted_requires + direct_requires
    total_ensures = dotted_ensures + direct_ensures

    result = {
        'has_require': total_requires > 0,
        'has_ensure': total_ensures > 0,
        'decorator_count': total_requires + total_ensures,
    }

    logger.debug(f"Found {result['decorator_count']} icontract decorators "
                 f"(requires={total_requires}, ensures={total_ensures})")
    return result


def _remove_comments(source_text: str) -> str:
    """
    Remove Python comments and strings from source code to avoid false positives.

    This is a simple implementation that removes:
    - Line comments (# comment)
    - But preserves strings to avoid removing # inside strings

    Args:
        source_text: The full source code

    Returns:
        Source code with comments removed
    """
    lines = source_text.split('\n')
    result_lines = []

    for line in lines:
        # Simple heuristic: find the # comment marker, but skip if it's in a string
        # We'll look for # that is not inside a string literal
        in_string = False
        string_char = None
        cleaned_line = []
        i = 0

        while i < len(line):
            char = line[i]

            # Handle string delimiters
            if char in ('"', "'") and (i == 0 or line[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                cleaned_line.append(char)
            # Handle comments
            elif char == '#' and not in_string:
                # Rest of the line is a comment
                break
            else:
                cleaned_line.append(char)

            i += 1

        result_lines.append(''.join(cleaned_line))

    return '\n'.join(result_lines)
