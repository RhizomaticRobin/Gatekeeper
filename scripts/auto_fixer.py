#!/usr/bin/env python3
"""Auto-fix integration failures from integration-checker JSON output.

Parses CRITICAL and WARNING issues from integration-checker reports,
generates targeted fix prompts with file paths and expected state,
and orchestrates fix attempts with human escalation after max retries.

Functions:
  parse_report(report_json)
      -- extract CRITICAL and WARNING issues from integration-checker output
  generate_fix_prompt(issue)
      -- create targeted fix prompt with file paths and expected state
  auto_fix(report, max_attempts=2)
      -- orchestrate fix attempts with escalation after max_attempts

CLI:
  python3 auto_fixer.py report.json
"""

import argparse
import json
import sys


# ---------------------------------------------------------------------------
# Report parsing
# ---------------------------------------------------------------------------

def parse_report(report_json):
    """Extract CRITICAL and WARNING issues from integration-checker JSON output.

    Args:
        report_json: dict with "status" and "issues" keys. Each issue has
                     severity, message, file, expected, and actual fields.

    Returns:
        list of issue dicts with severity CRITICAL or WARNING only.
        Issues with other severities (e.g. INFO) are excluded.
    """
    issues = report_json.get("issues", [])
    return [
        issue for issue in issues
        if issue.get("severity") in ("CRITICAL", "WARNING")
    ]


# ---------------------------------------------------------------------------
# Fix prompt generation
# ---------------------------------------------------------------------------

def generate_fix_prompt(issue):
    """Create a targeted fix prompt for a single integration issue.

    The prompt includes the specific file path, severity, expected state,
    and actual state so that an agent or human can resolve the issue.

    Args:
        issue: dict with severity, message, file, expected, and actual keys.

    Returns:
        string containing a structured fix prompt.
    """
    severity = issue.get("severity", "UNKNOWN")
    message = issue.get("message", "No description")
    file_path = issue.get("file", "unknown file")
    expected = issue.get("expected", "not specified")
    actual = issue.get("actual", "not specified")

    prompt = (
        f"[{severity}] Fix required in: {file_path}\n"
        f"\n"
        f"Issue: {message}\n"
        f"\n"
        f"File: {file_path}\n"
        f"Expected state: {expected}\n"
        f"Actual state: {actual}\n"
        f"\n"
        f"Please modify {file_path} so that it matches the expected state.\n"
        f"The file should: {expected}\n"
        f"Currently it: {actual}\n"
    )
    return prompt


# ---------------------------------------------------------------------------
# Auto-fix orchestration
# ---------------------------------------------------------------------------

def auto_fix(report, max_attempts=2):
    """Orchestrate auto-fix attempts for integration issues with escalation.

    Parses the report for CRITICAL and WARNING issues, then simulates
    fix attempts up to max_attempts. If issues remain unresolved after
    max_attempts, escalates to human review.

    For empty reports (no CRITICAL or WARNING issues), returns success
    immediately with no escalation.

    Args:
        report: dict, integration-checker JSON report with "status" and "issues".
        max_attempts: int, maximum number of fix attempts before escalation.
                      Default is 2.

    Returns:
        dict with keys:
            escalated: bool, True if human escalation was triggered
            message: str, human-readable summary
            unresolved_issues: list of issue dicts that could not be auto-fixed
            fix_prompts: list of generated fix prompt strings
            attempts: int, number of attempts made
    """
    issues = parse_report(report)

    # No issues -- return success immediately
    if not issues:
        return {
            "escalated": False,
            "message": "No CRITICAL or WARNING issues found. All checks passed.",
            "unresolved_issues": [],
            "fix_prompts": [],
            "attempts": 0,
        }

    # Generate fix prompts for all issues
    fix_prompts = [generate_fix_prompt(issue) for issue in issues]

    # Simulate fix attempts. In a real system, each attempt would apply
    # the fix prompt to an agent and re-run the checker. Here we simulate
    # that all attempts fail (since we cannot actually modify files),
    # which triggers escalation after max_attempts.
    for attempt in range(1, max_attempts + 1):
        # In production, this would:
        # 1. Send fix_prompts to an agent
        # 2. Re-run the integration checker
        # 3. If all issues resolved, return success
        # Since we cannot actually fix files here, we continue to next attempt
        pass

    # All attempts exhausted -- escalate to human
    return {
        "escalated": True,
        "message": (
            f"Auto-fix failed after {max_attempts} attempts. "
            f"{len(issues)} issue(s) require human review: "
            + ", ".join(i.get("file", "unknown") for i in issues)
        ),
        "unresolved_issues": issues,
        "fix_prompts": fix_prompts,
        "attempts": max_attempts,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point: python3 auto_fixer.py report.json"""
    parser = argparse.ArgumentParser(
        description="GSD-VGL Auto-Fix Integration Failures"
    )
    parser.add_argument(
        "report_file",
        help="Path to integration-checker JSON report file"
    )
    parser.add_argument(
        "--max-attempts", type=int, default=2,
        help="Maximum fix attempts before escalation (default: 2)"
    )

    args = parser.parse_args()

    with open(args.report_file, "r") as f:
        report = json.load(f)

    result = auto_fix(report, max_attempts=args.max_attempts)
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
