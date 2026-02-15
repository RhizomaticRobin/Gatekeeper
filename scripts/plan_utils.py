#!/usr/bin/env python3
"""Shared utilities for GSD-VGL plan orchestration.

Functions:
  load_plan(path)           — parse YAML, return dict
  find_task(plan, task_id)  — locate task by ID
  update_task_status(path, task_id, status) — update status in-place
  get_next_task(plan)       — first pending task with all deps completed
  get_all_unblocked_tasks(plan) — ALL pending tasks with all deps completed
  get_all_task_ids(plan)    — flat list of IDs
  topological_sort(plan)    — check for cycles (Kahn's algorithm)
  get_task_must_haves(plan, task_id) — get must_haves for a task
  get_phase_must_haves(plan, phase_id) — get must_haves for a phase
  get_task_wave(plan, task_id) — get wave assignment for a task
  get_model_profile(plan) — get model_profile from metadata

Also usable as CLI:
  python3 plan_utils.py <plan.yaml> --complete-task <task_id>
  python3 plan_utils.py <plan.yaml> --start-task <task_id>
  python3 plan_utils.py <plan.yaml> --next-task
  python3 plan_utils.py <plan.yaml> --unblocked-tasks
  python3 plan_utils.py <plan.yaml> --all-ids
"""

import sys
import os
import json
import re
import fcntl
import tempfile
from contextlib import contextmanager
from collections import deque

try:
    import yaml
except ImportError:
    yaml = None


@contextmanager
def _plan_lock(plan_path):
    """Acquire an exclusive flock on plan_path + '.lock'.

    Uses the same lock file that Bash flock uses in transition-task.sh,
    ensuring mutual exclusion between Python and Bash writers.

    When GSD_VGL_PLAN_LOCKED=1 is set in the environment (by a parent
    Bash process that already holds the flock), this becomes a no-op
    to avoid deadlock between parent shell flock and child Python flock.
    """
    lock_path = plan_path + ".lock"
    if os.environ.get("GSD_VGL_PLAN_LOCKED") == "1":
        # Parent process already holds the lock -- skip to avoid deadlock
        yield lock_path
        return
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield lock_path
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _parse_yaml_minimal(text):
    """Minimal YAML parser sufficient for plan.yaml structure.
    Falls back to this when PyYAML is not installed."""
    try:
        import yaml as _y
        return _y.safe_load(text)
    except ImportError:
        pass
    raise RuntimeError(
        "PyYAML is required. Install with: pip install pyyaml"
    )


def load_plan(path):
    """Parse plan.yaml and return dict."""
    with open(path, "r") as f:
        text = f.read()
    if yaml:
        return yaml.safe_load(text)
    return _parse_yaml_minimal(text)


def save_plan(path, plan):
    """Write plan dict back to YAML file.

    Uses exclusive flock for mutual exclusion and writes to a tempfile
    followed by os.replace for atomicity.
    """
    if yaml is None:
        raise RuntimeError("PyYAML is required for writing. Install with: pip install pyyaml")
    with _plan_lock(path):
        _atomic_write_plan(path, plan)


def _atomic_write_plan(path, plan):
    """Write plan to path atomically using tempfile + os.replace.

    Must be called while holding the plan lock.
    """
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(plan, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        os.replace(tmp_path, path)
    except BaseException:
        # Clean up temp file on error
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_all_task_ids(plan):
    """Return flat list of all task IDs in the plan."""
    ids = []
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            ids.append(str(task["id"]))
    return ids


def find_task(plan, task_id):
    """Locate a task by ID. Returns (phase, task) tuple or (None, None)."""
    task_id = str(task_id)
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            if str(task["id"]) == task_id:
                return phase, task
    return None, None


def update_task_status(path, task_id, status):
    """Update a task's status in-place and save.

    Acquires exclusive lock spanning the entire read-modify-write cycle
    to prevent concurrent corruption.
    """
    task_id = str(task_id)
    with _plan_lock(path):
        plan = load_plan(path)
        for phase in plan.get("phases", []):
            for task in phase.get("tasks", []):
                if str(task["id"]) == task_id:
                    task["status"] = status
                    _atomic_write_plan(path, plan)
                    return True
    return False


def get_next_task(plan):
    """Find first pending task where all depends_on are completed.
    Returns task dict or None."""
    completed = set()
    all_tasks = []
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            all_tasks.append(task)
            if task.get("status") == "completed":
                completed.add(str(task["id"]))

    for task in all_tasks:
        if task.get("status") != "pending":
            continue
        deps = [str(d) for d in task.get("depends_on", [])]
        if all(d in completed for d in deps):
            return task
    return None


def get_all_unblocked_tasks(plan):
    """Find ALL pending tasks where all depends_on are completed."""
    completed = set()
    all_tasks = []
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            all_tasks.append(task)
            if task.get("status") == "completed":
                completed.add(str(task["id"]))

    unblocked = []
    for task in all_tasks:
        if task.get("status") != "pending":
            continue
        deps = [str(d) for d in task.get("depends_on", [])]
        if all(d in completed for d in deps):
            unblocked.append(task)
    return unblocked


def topological_sort(plan):
    """Check for dependency cycles using Kahn's algorithm.
    Returns (sorted_ids, has_cycle) tuple.
    has_cycle is True if a cycle was detected."""
    all_ids = set(get_all_task_ids(plan))
    in_degree = {tid: 0 for tid in all_ids}
    adjacency = {tid: [] for tid in all_ids}

    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            tid = str(task["id"])
            for dep in task.get("depends_on", []):
                dep = str(dep)
                if dep in all_ids:
                    adjacency[dep].append(tid)
                    in_degree[tid] += 1

    queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
    sorted_ids = []

    while queue:
        node = queue.popleft()
        sorted_ids.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    has_cycle = len(sorted_ids) != len(all_ids)
    return sorted_ids, has_cycle


def get_task_must_haves(plan, task_id):
    """Get must_haves for a specific task. Returns dict or empty dict."""
    _, task = find_task(plan, task_id)
    if task is None:
        return {}
    return task.get("must_haves", {})


def get_phase_must_haves(plan, phase_id):
    """Get must_haves for a specific phase. Returns dict or empty dict."""
    phase_id = str(phase_id)
    for phase in plan.get("phases", []):
        if str(phase.get("id")) == phase_id:
            return phase.get("must_haves", {})
    return {}


def get_task_wave(plan, task_id):
    """Get wave assignment for a task. Returns int or None."""
    _, task = find_task(plan, task_id)
    if task is None:
        return None
    return task.get("wave")


def get_model_profile(plan):
    """Get model_profile from plan metadata. Returns string or 'default'."""
    return plan.get("metadata", {}).get("model_profile", "default")


def task_to_json(task):
    """Convert task dict to JSON-serializable form."""
    if task is None:
        return None
    return {
        "id": str(task["id"]),
        "name": task.get("name", ""),
        "status": task.get("status", "pending"),
        "depends_on": [str(d) for d in task.get("depends_on", [])],
        "deliverables": task.get("deliverables", {}),
        "tests": task.get("tests", {}),
        "prompt_file": task.get("prompt_file", ""),
        "must_haves": task.get("must_haves", {}),
        "file_scope": task.get("file_scope", {}),
        "wave": task.get("wave"),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GSD-VGL Plan Utilities")
    parser.add_argument("plan_file", help="Path to plan.yaml")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--complete-task", metavar="TASK_ID",
                       help="Mark task as completed")
    group.add_argument("--start-task", metavar="TASK_ID",
                       help="Mark task as in_progress")
    group.add_argument("--next-task", action="store_true",
                       help="Output next unblocked task as JSON")
    group.add_argument("--all-ids", action="store_true",
                       help="Output all task IDs")
    group.add_argument("--find-task", metavar="TASK_ID",
                       help="Find and output task as JSON")
    group.add_argument("--unblocked-tasks", action="store_true",
                       help="Output all unblocked tasks as JSON array")
    group.add_argument("--task-must-haves", metavar="TASK_ID",
                       help="Output must_haves for a task as JSON")
    group.add_argument("--phase-must-haves", metavar="PHASE_ID",
                       help="Output must_haves for a phase as JSON")

    args = parser.parse_args()

    if args.complete_task:
        ok = update_task_status(args.plan_file, args.complete_task, "completed")
        if ok:
            print(json.dumps({"status": "completed", "task_id": args.complete_task}))
        else:
            print(json.dumps({"error": f"Task {args.complete_task} not found"}),
                  file=sys.stderr)
            sys.exit(1)

    elif args.start_task:
        ok = update_task_status(args.plan_file, args.start_task, "in_progress")
        if ok:
            print(json.dumps({"status": "in_progress", "task_id": args.start_task}))
        else:
            print(json.dumps({"error": f"Task {args.start_task} not found"}),
                  file=sys.stderr)
            sys.exit(1)

    elif args.next_task:
        plan = load_plan(args.plan_file)
        task = get_next_task(plan)
        print(json.dumps(task_to_json(task)))

    elif args.all_ids:
        plan = load_plan(args.plan_file)
        print(json.dumps(get_all_task_ids(plan)))

    elif args.find_task:
        plan = load_plan(args.plan_file)
        _, task = find_task(plan, args.find_task)
        print(json.dumps(task_to_json(task)))

    elif args.unblocked_tasks:
        plan = load_plan(args.plan_file)
        tasks = get_all_unblocked_tasks(plan)
        print(json.dumps([task_to_json(t) for t in tasks]))

    elif args.task_must_haves:
        plan = load_plan(args.plan_file)
        print(json.dumps(get_task_must_haves(plan, args.task_must_haves)))

    elif args.phase_must_haves:
        plan = load_plan(args.plan_file)
        print(json.dumps(get_phase_must_haves(plan, args.phase_must_haves)))


if __name__ == "__main__":
    main()
