#!/usr/bin/env python3
"""Output ALL unblocked tasks from a GSD-VGL plan as a JSON array.

Usage:
  python3 get-unblocked-tasks.py <plan.yaml>

Outputs JSON array to stdout:
  - Array of task objects where all depends_on are completed
  - Empty array [] if no tasks are available
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plan_utils import load_plan, get_all_unblocked_tasks, task_to_json


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 get-unblocked-tasks.py <plan.yaml>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        plan = load_plan(path)
    except Exception as e:
        print(f"Error loading plan: {e}", file=sys.stderr)
        sys.exit(1)

    tasks = get_all_unblocked_tasks(plan)
    print(json.dumps([task_to_json(t) for t in tasks]))


if __name__ == "__main__":
    main()
