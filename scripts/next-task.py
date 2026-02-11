#!/usr/bin/env python3
"""Output the next unblocked task from a GSD-VGL plan as JSON.

Usage:
  python3 next-task.py <plan.yaml>

Outputs JSON to stdout:
  - Task object if a pending unblocked task exists
  - null if no tasks are available
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plan_utils import load_plan, get_next_task, task_to_json


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 next-task.py <plan.yaml>", file=sys.stderr)
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

    task = get_next_task(plan)
    print(json.dumps(task_to_json(task)))


if __name__ == "__main__":
    main()
