#!/usr/bin/env python3
"""Check file_scope overlaps between tasks to determine safe parallelism.

Usage:
  python3 check-file-conflicts.py <plan.yaml> <task_id1> <task_id2> [<task_id3> ...]

Reads file_scope.owns for each task and detects overlapping paths.

Output JSON:
  {
    "safe_parallel": ["2.1", "2.2"],
    "sequential_fallback": ["3.1"],
    "conflicts": [{"tasks": ["2.1", "3.1"], "path": "src/components/menu/"}]
  }

Tasks without file_scope are placed in sequential_fallback (assumed to touch any file).
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plan_utils import load_plan, find_task


def paths_overlap(path_a, path_b):
    """Check if two file/directory paths overlap.
    A path overlaps if one is a prefix of the other, or they are equal."""
    a = path_a.rstrip("/") + "/"
    b = path_b.rstrip("/") + "/"
    return a.startswith(b) or b.startswith(a) or path_a == path_b


def check_conflicts(plan, task_ids):
    """Partition task_ids into safe_parallel and sequential_fallback groups."""
    tasks_with_scope = {}
    tasks_without_scope = []

    for tid in task_ids:
        _, task = find_task(plan, tid)
        if task is None:
            continue
        scope = task.get("file_scope")
        if scope and isinstance(scope, dict) and "owns" in scope:
            owns = scope["owns"]
            if isinstance(owns, list) and len(owns) > 0:
                tasks_with_scope[str(tid)] = owns
                continue
        tasks_without_scope.append(str(tid))

    conflicts = []
    conflicting_tasks = set()

    scoped_ids = list(tasks_with_scope.keys())
    for i in range(len(scoped_ids)):
        for j in range(i + 1, len(scoped_ids)):
            tid_a = scoped_ids[i]
            tid_b = scoped_ids[j]
            for path_a in tasks_with_scope[tid_a]:
                for path_b in tasks_with_scope[tid_b]:
                    if paths_overlap(path_a, path_b):
                        conflicts.append({
                            "tasks": [tid_a, tid_b],
                            "path": path_a if len(path_a) <= len(path_b) else path_b,
                        })
                        conflicting_tasks.add(tid_a)
                        conflicting_tasks.add(tid_b)

    safe_parallel = [tid for tid in scoped_ids if tid not in conflicting_tasks]
    sequential_fallback = list(conflicting_tasks) + tasks_without_scope

    return {
        "safe_parallel": safe_parallel,
        "sequential_fallback": sequential_fallback,
        "conflicts": conflicts,
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 check-file-conflicts.py <plan.yaml> <task_id1> [<task_id2> ...]",
              file=sys.stderr)
        sys.exit(1)

    plan_path = sys.argv[1]
    task_ids = sys.argv[2:]

    if not os.path.isfile(plan_path):
        print(f"Error: file not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    try:
        plan = load_plan(plan_path)
    except Exception as e:
        print(f"Error loading plan: {e}", file=sys.stderr)
        sys.exit(1)

    result = check_conflicts(plan, task_ids)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
