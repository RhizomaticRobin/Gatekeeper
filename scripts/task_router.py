#!/usr/bin/env python3
"""Task type detection and agent routing for GSD-VGL.

Detects the type of a task based on file_scope.owns patterns and returns
type-specific agent guidance (prompt additions with best practices).

Functions:
  detect_task_type(task)      -- returns one of: api, ui, data, infra, test, script, general
  get_agent_guidance(task_type) -- returns prompt additions with type-specific best practices

CLI:
  python3 task_router.py plan.yaml TASK_ID
  Outputs JSON: {"task_type": "...", "guidance": "..."}
"""

import json
import os
import sys

try:
    import yaml
except ImportError:
    yaml = None


# ---------------------------------------------------------------------------
# File-pattern heuristics for task type detection
# ---------------------------------------------------------------------------

# Each entry: (task_type, list_of_patterns)
# Patterns are matched against the beginning of each file path in file_scope.owns.
# The first matching type wins (order matters for priority).
_TYPE_PATTERNS = [
    ("api", ["routes/", "endpoints/", "api/"]),
    ("ui", ["components/", "pages/", "templates/"]),
    ("data", ["models/", "schema", "migrations/"]),
    ("infra", ["scripts/", "config/", "deploy/"]),
    ("test", ["tests/", "test_"]),
    ("script", ["hooks/", "bin/"]),
]


def detect_task_type(task):
    """Detect the type of a task based on file_scope.owns patterns.

    Args:
        task: A task dict that may contain a 'file_scope' key with an 'owns' list.

    Returns:
        One of: 'api', 'ui', 'data', 'infra', 'test', 'script', 'general'.
        Defaults to 'general' if no patterns match or no file_scope is present.
    """
    file_scope = task.get("file_scope", {})
    owns = file_scope.get("owns", []) if file_scope else []

    if not owns:
        return "general"

    # Count matches per type
    type_counts = {}
    for file_path in owns:
        for task_type, patterns in _TYPE_PATTERNS:
            for pattern in patterns:
                if file_path.startswith(pattern) or ("/" + pattern) in file_path:
                    type_counts[task_type] = type_counts.get(task_type, 0) + 1
                    break
            else:
                continue
            break  # matched a type for this file, move to next file

    if not type_counts:
        return "general"

    # Return the type with the most matches
    return max(type_counts, key=type_counts.get)


# ---------------------------------------------------------------------------
# Agent guidance per task type
# ---------------------------------------------------------------------------

_GUIDANCE = {
    "api": (
        "API Task Guidance:\n"
        "- Follow RESTful conventions for route naming and HTTP methods.\n"
        "- Include request validation and proper error responses (4xx/5xx).\n"
        "- Add OpenAPI/Swagger documentation annotations where applicable.\n"
        "- Write integration tests that cover happy path and error cases.\n"
        "- Ensure proper authentication/authorization middleware is applied."
    ),
    "ui": (
        "UI Task Guidance:\n"
        "- Use component-based architecture with clear prop interfaces.\n"
        "- Ensure accessibility (ARIA labels, keyboard navigation, contrast).\n"
        "- Handle loading, error, and empty states in all components.\n"
        "- Write visual regression tests or snapshot tests.\n"
        "- Follow responsive design principles for mobile compatibility."
    ),
    "data": (
        "Data Task Guidance:\n"
        "- Define clear schema with proper types, constraints, and indexes.\n"
        "- Write reversible migrations with both up and down operations.\n"
        "- Validate data at the model layer before persistence.\n"
        "- Include seed data or fixtures for development and testing.\n"
        "- Consider query performance and add appropriate indexes."
    ),
    "infra": (
        "Infrastructure Task Guidance:\n"
        "- Make scripts idempotent so they can be safely re-run.\n"
        "- Use environment variables for configuration, never hard-code secrets.\n"
        "- Add health checks and monitoring hooks where appropriate.\n"
        "- Document deployment steps and rollback procedures.\n"
        "- Ensure scripts work across target environments (dev, staging, prod)."
    ),
    "test": (
        "Test Task Guidance:\n"
        "- Follow Arrange-Act-Assert (AAA) pattern for test structure.\n"
        "- Cover happy path, edge cases, and error conditions.\n"
        "- Use descriptive test names that explain the expected behavior.\n"
        "- Mock external dependencies to keep tests fast and isolated.\n"
        "- Ensure tests are deterministic and do not depend on execution order."
    ),
    "script": (
        "Script/Hook Task Guidance:\n"
        "- Add usage documentation and --help flag support.\n"
        "- Handle errors gracefully with meaningful exit codes.\n"
        "- Make scripts portable across common shell environments.\n"
        "- Add input validation for all arguments and flags.\n"
        "- Log progress and results for debugging and auditing."
    ),
    "general": (
        "General Task Guidance:\n"
        "- Follow the project's established coding conventions and patterns.\n"
        "- Write clear, self-documenting code with meaningful names.\n"
        "- Add inline comments only for non-obvious logic.\n"
        "- Ensure changes are backward-compatible where possible.\n"
        "- Include appropriate tests for all new functionality."
    ),
}


def get_agent_guidance(task_type):
    """Return prompt additions with type-specific best practices.

    Args:
        task_type: One of 'api', 'ui', 'data', 'infra', 'test', 'script', 'general'.

    Returns:
        A string with agent guidance appropriate for the task type.
        Falls back to 'general' guidance for unknown types.
    """
    return _GUIDANCE.get(task_type, _GUIDANCE["general"])


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point.

    Usage: python3 task_router.py plan.yaml TASK_ID
    Output: JSON object with task_type and guidance.
    """
    if len(sys.argv) < 3:
        print(
            "Usage: python3 task_router.py <plan.yaml> <TASK_ID>",
            file=sys.stderr,
        )
        sys.exit(1)

    plan_path = sys.argv[1]
    task_id = sys.argv[2]

    # Load the plan
    if yaml is None:
        print("Error: PyYAML is required. Install with: pip install pyyaml",
              file=sys.stderr)
        sys.exit(1)

    with open(plan_path, "r") as f:
        plan = yaml.safe_load(f)

    # Find the task
    task_id_str = str(task_id)
    found_task = None
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task["id"]) == task_id_str:
                found_task = task
                break
        if found_task:
            break

    if found_task is None:
        print(json.dumps({"error": f"Task {task_id} not found"}), file=sys.stderr)
        sys.exit(1)

    task_type = detect_task_type(found_task)
    guidance = get_agent_guidance(task_type)

    output = {
        "task_type": task_type,
        "guidance": guidance,
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
