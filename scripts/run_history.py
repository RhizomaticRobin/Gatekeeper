#!/usr/bin/env python3
"""Run history database for Gatekeeper task execution tracking.

Provides persistent JSONL-based storage for recording task execution outcomes
and querying aggregate statistics.

Functions:
  record_outcome(task_id, iterations, passed, duration_seconds, ...)
      — append a JSON entry to .planning/history/runs.jsonl
  get_history(task_id=None, history_dir=None)
      — return list of records, optionally filtered by task_id
  get_all_history(history_dir=None)
      — return all records
  get_stats(history_dir=None)
      — compute aggregate stats: avg iterations, pass rate, avg duration
  detect_patterns(history, min_occurrences=3)
      — find recurring failure patterns grouped by file scope and error type

CLI:
  python3 run_history.py --record --task-id T --iterations N --passed --duration D
  python3 run_history.py --query TASK_ID
  python3 run_history.py --stats
  python3 run_history.py --patterns [--history-dir DIR] [--min-occurrences N]

Storage: .planning/history/runs.jsonl (one JSON object per line)
Record schema: {"task_id", "iterations", "passed", "duration_s",
                "failure_reasons", "session_id", "timestamp"}
"""

import argparse
import collections
import fcntl
import hashlib
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone


# Default history directory relative to the project root
_DEFAULT_HISTORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".planning", "history"
)

_HISTORY_FILENAME = "runs.jsonl"


@contextmanager
def _history_lock(history_dir):
    """Acquire an exclusive flock on the history lock file for thread safety."""
    lock_path = os.path.join(history_dir, "runs.jsonl.lock")
    os.makedirs(history_dir, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _history_path(history_dir=None):
    """Return the full path to the JSONL history file."""
    hdir = history_dir or _DEFAULT_HISTORY_DIR
    return os.path.join(hdir, _HISTORY_FILENAME)


def record_outcome(task_id, iterations, passed, duration_seconds,
                   failure_reasons=None, session_id=None, history_dir=None):
    """Append a run outcome record to the JSONL history file.

    Args:
        task_id: The task identifier (e.g. "1.1", "2.3")
        iterations: Number of verifier iterations
        passed: Whether the task passed verification
        duration_seconds: Wall-clock duration in seconds
        failure_reasons: Optional list of failure reason strings
        session_id: Optional session identifier
        history_dir: Optional override for the history directory
    """
    hdir = history_dir or _DEFAULT_HISTORY_DIR
    filepath = _history_path(hdir)

    record = {
        "task_id": str(task_id),
        "iterations": int(iterations),
        "passed": bool(passed),
        "duration_s": float(duration_seconds),
        "failure_reasons": failure_reasons if failure_reasons is not None else [],
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(hdir, exist_ok=True)

    with _history_lock(hdir):
        with open(filepath, "a") as f:
            f.write(json.dumps(record) + "\n")


def get_history(task_id=None, history_dir=None):
    """Return list of history records, optionally filtered by task_id.

    Args:
        task_id: If provided, only return records matching this task_id
        history_dir: Optional override for the history directory

    Returns:
        List of record dicts
    """
    all_records = get_all_history(history_dir=history_dir)
    if task_id is not None:
        task_id = str(task_id)
        return [r for r in all_records if r.get("task_id") == task_id]
    return all_records


def get_all_history(history_dir=None):
    """Return all history records.

    Args:
        history_dir: Optional override for the history directory

    Returns:
        List of all record dicts
    """
    filepath = _history_path(history_dir)
    if not os.path.exists(filepath):
        return []

    records = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def get_stats(history_dir=None):
    """Compute aggregate statistics from run history.

    Returns a dict with:
        total_runs: int
        avg_iterations: float
        pass_rate: float (0.0 to 1.0)
        avg_duration_s: float
        per_task: dict mapping task_id to per-task stats

    Args:
        history_dir: Optional override for the history directory
    """
    records = get_all_history(history_dir=history_dir)

    if not records:
        return {
            "total_runs": 0,
            "avg_iterations": 0,
            "pass_rate": 0,
            "avg_duration_s": 0,
            "per_task": {},
        }

    total = len(records)
    total_iterations = sum(r.get("iterations", 0) for r in records)
    total_passed = sum(1 for r in records if r.get("passed"))
    total_duration = sum(r.get("duration_s", 0) for r in records)

    # Per-task breakdowns
    per_task = {}
    for r in records:
        tid = r.get("task_id", "unknown")
        if tid not in per_task:
            per_task[tid] = {
                "runs": 0,
                "total_iterations": 0,
                "passed": 0,
                "total_duration_s": 0,
            }
        per_task[tid]["runs"] += 1
        per_task[tid]["total_iterations"] += r.get("iterations", 0)
        if r.get("passed"):
            per_task[tid]["passed"] += 1
        per_task[tid]["total_duration_s"] += r.get("duration_s", 0)

    # Compute per-task averages
    for tid, data in per_task.items():
        runs = data["runs"]
        data["avg_iterations"] = data["total_iterations"] / runs
        data["pass_rate"] = data["passed"] / runs
        data["avg_duration_s"] = data["total_duration_s"] / runs

    return {
        "total_runs": total,
        "avg_iterations": total_iterations / total,
        "pass_rate": total_passed / total,
        "avg_duration_s": total_duration / total,
        "per_task": per_task,
    }


def _extract_file_scope(reason):
    """Extract a file scope (file path) from a failure reason string.

    Looks for patterns like "failure in <path>" or embedded file paths with
    directory separators and extensions.

    Returns the matched file path string or None.
    """
    # Pattern 1: "... in <filepath>"
    m = re.search(r'(?:in|at|from)\s+(\S+/\S+\.\S+)', reason)
    if m:
        return m.group(1)
    # Pattern 2: bare file path with at least one directory separator
    m = re.search(r'(\S+/\S+\.\S+)', reason)
    if m:
        return m.group(1)
    return None


def _extract_error_category(reason):
    """Extract the error category (e.g. 'TypeError') from a failure reason.

    Looks for CamelCase error type prefixes (ending in 'Error', 'Exception',
    'Warning', 'Fault') or a colon-separated prefix.

    Returns the matched category string or 'unknown'.
    """
    # Pattern 1: "ErrorType: ..." at the start
    m = re.match(r'^(\w+(?:Error|Exception|Warning|Fault))\s*:', reason)
    if m:
        return m.group(1)
    # Pattern 2: anywhere in the string
    m = re.search(r'(\w+(?:Error|Exception|Warning|Fault))', reason)
    if m:
        return m.group(1)
    return "unknown"


def detect_patterns(history, min_occurrences=3):
    """Detect recurring failure patterns in history records.

    Groups failed records by (file_scope, error_category) extracted from
    failure_reasons, and returns groups that occur >= min_occurrences times.

    Patterns are project-scoped: the caller passes in project-specific history.

    Args:
        history: list of record dicts (from get_all_history)
        min_occurrences: minimum count to flag a pattern (default 3)

    Returns:
        list of pattern dicts with keys:
            file_scope: the file path associated with the failure
            error_category: the error type (e.g. TypeError)
            count: number of occurrences
            task_ids: list of task_ids that hit this pattern
    """
    if not history:
        return []

    # Group by (file_scope, error_category)
    groups = collections.defaultdict(lambda: {"count": 0, "task_ids": []})

    for record in history:
        if record.get("passed"):
            continue  # only look at failures

        for reason in record.get("failure_reasons", []):
            file_scope = _extract_file_scope(reason)
            error_category = _extract_error_category(reason)

            if file_scope is None:
                continue  # cannot determine scope

            key = (file_scope, error_category)
            groups[key]["count"] += 1
            task_id = record.get("task_id", "unknown")
            if task_id not in groups[key]["task_ids"]:
                groups[key]["task_ids"].append(task_id)

    # Filter by min_occurrences
    patterns = []
    for (file_scope, error_category), data in groups.items():
        if data["count"] >= min_occurrences:
            patterns.append({
                "file_scope": file_scope,
                "error_category": error_category,
                "count": data["count"],
                "task_ids": data["task_ids"],
            })

    # Sort by count descending for consistent output
    patterns.sort(key=lambda p: p["count"], reverse=True)
    return patterns


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Gatekeeper Run History Database"
    )
    parser.add_argument(
        "--history-dir",
        default=None,
        help="Override history directory (default: .planning/history/)"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", action="store_true",
                       help="Record a new run outcome")
    group.add_argument("--query", metavar="TASK_ID",
                       help="Query history for a task")
    group.add_argument("--stats", action="store_true",
                       help="Show aggregate statistics")
    group.add_argument("--patterns", action="store_true",
                       help="Detect recurring failure patterns")

    # Record-specific arguments
    parser.add_argument("--task-id", help="Task ID for --record")
    parser.add_argument("--iterations", type=int, help="Iterations for --record")
    parser.add_argument("--passed", action="store_true",
                        help="Task passed for --record")
    parser.add_argument("--duration", type=float,
                        help="Duration in seconds for --record")
    parser.add_argument("--failure-reasons", nargs="*",
                        help="Failure reasons for --record")
    parser.add_argument("--session-id", help="Session ID for --record")
    parser.add_argument("--min-occurrences", type=int, default=3,
                        help="Minimum occurrences for --patterns (default: 3)")

    args = parser.parse_args()

    if args.record:
        if not all([args.task_id, args.iterations is not None, args.duration is not None]):
            parser.error("--record requires --task-id, --iterations, and --duration")
        record_outcome(
            task_id=args.task_id,
            iterations=args.iterations,
            passed=args.passed,
            duration_seconds=args.duration,
            failure_reasons=args.failure_reasons,
            session_id=args.session_id,
            history_dir=args.history_dir,
        )
        print(json.dumps({"status": "recorded", "task_id": args.task_id}))

    elif args.query:
        records = get_history(
            task_id=args.query,
            history_dir=args.history_dir,
        )
        print(json.dumps(records, indent=2))

    elif args.stats:
        stats = get_stats(history_dir=args.history_dir)
        print(json.dumps(stats, indent=2))

    elif args.patterns:
        all_history = get_all_history(history_dir=args.history_dir)
        patterns = detect_patterns(all_history, min_occurrences=args.min_occurrences)
        print(json.dumps(patterns, indent=2))


if __name__ == "__main__":
    main()
