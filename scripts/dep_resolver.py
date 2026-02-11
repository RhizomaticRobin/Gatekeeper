#!/usr/bin/env python3
"""Autonomous dependency resolution for GSD-VGL task execution.

Detects missing dependencies from error output and generates safe resolution
commands (install only, never remove/uninstall).

Functions:
  analyze_error(error_output)
      -- detect missing npm/pip packages from error patterns
  resolve(issues)
      -- generate safe resolution commands for detected issues
  detect_missing_env(error_output)
      -- find undefined environment variable references

Patterns:
  - "Cannot find module 'X'" -> npm install X
  - "ModuleNotFoundError: No module named 'X'" -> pip install X
  - "process.env.X is undefined" -> prompt for env var

CLI:
  python3 dep_resolver.py --analyze error.log
"""

import argparse
import json
import re
import sys


# ---------------------------------------------------------------------------
# Error analysis patterns
# ---------------------------------------------------------------------------

# Pattern: Cannot find module 'package-name' or Cannot find module '@scope/pkg'
# Excludes relative paths like './foo' or '../bar'
_NPM_MODULE_PATTERN = re.compile(
    r"Cannot find module '(?!\.\.?/)(@?[a-zA-Z0-9][\w./-]*)'"
)

# Pattern: ModuleNotFoundError: No module named 'package' or 'package.submod'
_PIP_MODULE_PATTERN = re.compile(
    r"ModuleNotFoundError: No module named '([a-zA-Z0-9_][a-zA-Z0-9_.]*)'",
)

# Pattern: process.env.VAR_NAME is undefined
_ENV_VAR_PATTERN = re.compile(
    r"process\.env\.([A-Z_][A-Z0-9_]*)\s+is\s+undefined",
)


def analyze_error(error_output):
    """Detect missing npm and pip packages from error output.

    Args:
        error_output: string containing build/test error output

    Returns:
        list of dicts, each with keys:
            type: "missing_npm" or "missing_pip"
            package: the package name to install
    """
    if not error_output:
        return []

    issues = []
    seen = set()

    # Detect missing npm modules
    for match in _NPM_MODULE_PATTERN.finditer(error_output):
        package = match.group(1)
        key = ("missing_npm", package)
        if key not in seen:
            seen.add(key)
            issues.append({
                "type": "missing_npm",
                "package": package,
            })

    # Detect missing pip modules
    for match in _PIP_MODULE_PATTERN.finditer(error_output):
        full_module = match.group(1)
        # Extract top-level package name (before first dot)
        package = full_module.split(".")[0]
        key = ("missing_pip", package)
        if key not in seen:
            seen.add(key)
            issues.append({
                "type": "missing_pip",
                "package": package,
            })

    return issues


def detect_missing_env(error_output):
    """Find undefined environment variable references in error output.

    Args:
        error_output: string containing build/test error output

    Returns:
        list of dicts, each with keys:
            type: "missing_env"
            variable: the environment variable name
    """
    if not error_output:
        return []

    issues = []
    seen = set()

    for match in _ENV_VAR_PATTERN.finditer(error_output):
        variable = match.group(1)
        if variable not in seen:
            seen.add(variable)
            issues.append({
                "type": "missing_env",
                "variable": variable,
            })

    return issues


def resolve(issues):
    """Generate safe resolution commands for detected dependency issues.

    Only generates install/prompt actions. Never generates remove or uninstall
    commands.

    Args:
        issues: list of issue dicts from analyze_error or detect_missing_env

    Returns:
        list of dicts, each with keys:
            action: "install" or "prompt"
            command: the shell command to run (or prompt message)
            package: the package/variable name
    """
    if not issues:
        return []

    actions = []

    for issue in issues:
        issue_type = issue.get("type")

        if issue_type == "missing_npm":
            package = issue["package"]
            actions.append({
                "action": "install",
                "command": f"npm install {package}",
                "package": package,
            })

        elif issue_type == "missing_pip":
            package = issue["package"]
            actions.append({
                "action": "install",
                "command": f"pip install {package}",
                "package": package,
            })

        elif issue_type == "missing_env":
            variable = issue["variable"]
            actions.append({
                "action": "prompt",
                "command": f"export {variable}=<value>",
                "variable": variable,
            })

    return actions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GSD-VGL Autonomous Dependency Resolution"
    )

    parser.add_argument(
        "--analyze",
        metavar="ERROR_LOG",
        help="Path to error log file to analyze for missing dependencies",
    )

    args = parser.parse_args()

    if args.analyze:
        try:
            with open(args.analyze, "r") as f:
                error_output = f.read()
        except FileNotFoundError:
            print(json.dumps({"error": f"File not found: {args.analyze}"}))
            sys.exit(1)

        # Detect all types of issues
        issues = analyze_error(error_output)
        env_issues = detect_missing_env(error_output)
        all_issues = issues + env_issues

        # Generate resolution actions
        actions = resolve(all_issues)

        result = {
            "issues": all_issues,
            "actions": actions,
        }
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
