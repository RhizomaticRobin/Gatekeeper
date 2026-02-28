"""
Parser for cargo-semver-checks text output.

Extracts structured breaking change information from the text output
that 'cargo semver-checks check-release' produces on stdout.

This is a pure parsing module with no external dependencies.
It is imported by semver.py to parse subprocess output.

Usage:
    from gatekeeper_mcp.tools.semver_parser import parse_semver_breaking_changes

    changes = parse_semver_breaking_changes(stdout_text)
    # [{'name': 'function_removed', 'summary': 'A previously-public function...', 'span_file': 'src/api.rs', 'span_line': 15}, ...]
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Regex patterns for cargo-semver-checks output
# Matches: --- failure <name> ---
FAILURE_HEADER_PATTERN = re.compile(r'^---\s+failure\s+(\S+)\s+---', re.MULTILINE)

# Matches: Summary: <text> or Description: <text>
SUMMARY_PATTERN = re.compile(r'(?:Summary|Description):\s*(.+)', re.IGNORECASE)

# Matches: span: path/to/file.rs:42:5 or span: path/to/file.rs:42
# Also matches: ref: path/to/file.rs:42
SPAN_PATTERN = re.compile(r'(?:span|ref):\s*(.+?):(\d+)(?::(\d+))?')

# Matches: name: <identifier>
NAME_LINE_PATTERN = re.compile(r'\s+name:\s*(.+)')


def parse_semver_breaking_changes(stdout: str) -> list[dict]:
    """
    Parse cargo-semver-checks stdout for breaking change items.

    Each breaking change becomes a dict with keys:
    - name: str (the lint/check name, e.g., 'function_removed')
    - summary: str (description of the breaking change)
    - span_file: str or None (source file path)
    - span_line: int or None (line number in source file)

    Args:
        stdout: The stdout output from cargo semver-checks

    Returns:
        List of breaking change dicts. Empty list if no breaking changes found.
    """
    if not stdout or not stdout.strip():
        return []

    changes = []

    # Find all failure header positions
    headers = list(FAILURE_HEADER_PATTERN.finditer(stdout))

    for idx, header_match in enumerate(headers):
        change_name = header_match.group(1)

        # Extract the block between this header and the next (or end of string)
        start = header_match.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(stdout)
        block = stdout[start:end]

        # Extract summary/description
        summary = ''
        summary_match = SUMMARY_PATTERN.search(block)
        if summary_match:
            summary = summary_match.group(1).strip()

        # Extract span/ref file and line
        span_file: Optional[str] = None
        span_line: Optional[int] = None
        span_match = SPAN_PATTERN.search(block)
        if span_match:
            span_file = span_match.group(1).strip()
            span_line = int(span_match.group(2))

        changes.append({
            'name': change_name,
            'summary': summary,
            'span_file': span_file,
            'span_line': span_line,
        })

    logger.debug(f"Parsed {len(changes)} breaking changes from semver-checks output")
    return changes
