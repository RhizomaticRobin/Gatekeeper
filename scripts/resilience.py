#!/usr/bin/env python3
"""Resilience module for Gatekeeper.

Provides:
  - Stuck detection (per-task consecutive failures)
  - Circuit breaker (total failures threshold)
  - Budget checks (iterations and timeout)
  - Failure pattern analysis
"""

import argparse
import fcntl
import json
import os
import sys
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

MAX_FAILURE_WINDOW = 20


# ---------------------------------------------------------------------------
# File-lock helper (matches evo_db.py pattern)
# ---------------------------------------------------------------------------

@contextmanager
def _state_lock(state_path: str):
    """Acquire an exclusive flock for thread-safe state access."""
    lock_path = state_path + ".lock"
    lock_dir = os.path.dirname(lock_path)
    if lock_dir:
        os.makedirs(lock_dir, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@dataclass
class ResilienceState:
    task_failures: Dict[str, int] = field(default_factory=dict)
    total_failures: int = 0
    failure_window: List[Dict[str, Any]] = field(default_factory=list)
    total_iterations: int = 0
    started_at: Optional[str] = None
    last_failure_task: Optional[str] = None


class ResilienceManager:
    def __init__(self, state_path: str):
        self.state_path = state_path
        self.state = ResilienceState()

    def record_failure(
        self,
        task_id: str,
        error: Optional[str] = None,
        files: Optional[List[str]] = None,
    ):
        if self.state.started_at is None:
            self.state.started_at = datetime.now().isoformat()

        self.state.task_failures[task_id] = self.state.task_failures.get(task_id, 0) + 1
        self.state.total_failures += 1
        self.state.last_failure_task = task_id

        entry = {
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
        }
        if error is not None:
            entry["error"] = error
        if files is not None:
            entry["files"] = files

        self.state.failure_window.append(entry)

        while len(self.state.failure_window) > MAX_FAILURE_WINDOW:
            self.state.failure_window.pop(0)

        self.save()

    def record_success(self, task_id: str):
        self.state.task_failures[task_id] = 0
        self.save()

    def check_stuck(self, task_id: str, threshold: int) -> Tuple[bool, int, str]:
        count = self.state.task_failures.get(task_id, 0)

        if count < threshold:
            return False, count, f"Gatekeeper: Task {task_id} ({count} failures, below threshold {threshold})"

        # Examine recent error messages for this task
        recent_errors = []
        for entry in reversed(self.state.failure_window):
            if entry.get("task_id") == task_id and "error" in entry:
                recent_errors.append(entry["error"])
                if len(recent_errors) >= count:
                    break

        if not recent_errors:
            # No error messages recorded — fall back to count-based
            is_stuck = count >= threshold
            msg = f"Gatekeeper: Stuck on task {task_id} ({count} consecutive failures, threshold: {threshold})"
            return is_stuck, count, msg

        unique_errors = set(recent_errors[:threshold])

        if len(unique_errors) <= 1:
            # All recent errors identical — truly stuck
            msg = f"Gatekeeper: Stuck on task {task_id} ({count} identical consecutive failures, threshold: {threshold})"
            return True, count, msg
        else:
            # Diverse errors — still making progress, extend threshold
            extended_threshold = threshold * 2
            is_stuck = count >= extended_threshold
            msg = (
                f"Gatekeeper: Task {task_id} has {count} consecutive failures "
                f"({len(unique_errors)} distinct errors, extended threshold: {extended_threshold})"
            )
            return is_stuck, count, msg

    def check_circuit_breaker(self, threshold: int) -> Tuple[bool, int, str]:
        count = self.state.total_failures
        is_tripped = count >= threshold
        msg = f"Gatekeeper: Circuit breaker tripped ({count} total failures, threshold: {threshold})"
        return is_tripped, count, msg

    def check_budget(
        self, max_iterations: int, timeout_hours: int
    ) -> Tuple[bool, Optional[str], str]:
        if self.state.total_iterations >= max_iterations:
            msg = f"Gatekeeper: Budget exceeded ({self.state.total_iterations} iterations, max: {max_iterations})"
            return True, "iterations", msg

        if self.state.started_at is not None:
            started = datetime.fromisoformat(self.state.started_at)
            elapsed = datetime.now() - started
            elapsed_hours = elapsed.total_seconds() / 3600
            if elapsed_hours >= timeout_hours:
                msg = f"Gatekeeper: Budget exceeded ({elapsed_hours:.1f} hours elapsed, max: {timeout_hours})"
                return True, "timeout", msg

        return False, None, ""

    def analyze_failures(self) -> Dict[str, Any]:
        result = {
            "repeated_errors": [],
            "affected_files": [],
            "failing_phases": [],
        }

        if not self.state.failure_window:
            return result

        error_counts = Counter()
        file_counts = Counter()
        phase_counts = Counter()

        for entry in self.state.failure_window:
            if "error" in entry:
                error_counts[entry["error"]] += 1
            if "files" in entry:
                for f in entry["files"]:
                    file_counts[f] += 1
            task_id = entry.get("task_id", "")
            if "." in task_id:
                phase = task_id.split(".")[0]
                phase_counts[phase] += 1

        for error, count in error_counts.most_common():
            result["repeated_errors"].append({"error": error, "count": count})

        for file, count in file_counts.most_common():
            result["affected_files"].append({"file": file, "count": count})

        for phase, count in phase_counts.most_common():
            result["failing_phases"].append({"phase": phase, "count": count})

        return result

    def check_all(
        self, task_id: str, config: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        stuck_threshold = config.get("stuck_threshold", 10)
        circuit_breaker_threshold = config.get("circuit_breaker_threshold", 10)
        max_iterations = config.get("max_gatekeeper_iterations", 50)
        timeout_hours = config.get("timeout_hours", 8)

        is_stuck, _, stuck_msg = self.check_stuck(task_id, stuck_threshold)
        if is_stuck:
            return True, "stuck", stuck_msg

        is_tripped, _, trip_msg = self.check_circuit_breaker(circuit_breaker_threshold)
        if is_tripped:
            return True, "circuit_breaker", trip_msg

        exceeded, reason, budget_msg = self.check_budget(max_iterations, timeout_hours)
        if exceeded:
            return True, reason, budget_msg

        return False, None, None

    def reset(self):
        self.state = ResilienceState()
        self.save()

    def save(self):
        data = {
            "task_failures": self.state.task_failures,
            "total_failures": self.state.total_failures,
            "failure_window": self.state.failure_window,
            "total_iterations": self.state.total_iterations,
            "started_at": self.state.started_at,
            "last_failure_task": self.state.last_failure_task,
        }
        dir_path = os.path.dirname(self.state_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        with _state_lock(self.state_path):
            with open(self.state_path, "w") as f:
                json.dump(data, f, indent=2)

    def load(self):
        if not os.path.exists(self.state_path):
            return
        with _state_lock(self.state_path):
            with open(self.state_path, "r") as f:
                data = json.load(f)
        self.state.task_failures = data.get("task_failures", {})
        self.state.total_failures = data.get("total_failures", 0)
        self.state.failure_window = data.get("failure_window", [])
        self.state.total_iterations = data.get("total_iterations", 0)
        self.state.started_at = data.get("started_at")
        self.state.last_failure_task = data.get("last_failure_task")


def main():
    parser = argparse.ArgumentParser(description="Gatekeeper Resilience Manager")
    parser.add_argument("--state-path", required=True, help="Path to state JSON file")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--record-failure", metavar="TASK_ID", help="Record a failure for a task"
    )
    group.add_argument(
        "--record-success", metavar="TASK_ID", help="Record a success for a task"
    )
    group.add_argument(
        "--check-stuck", metavar="TASK_ID", help="Check if task is stuck"
    )
    group.add_argument(
        "--check-circuit-breaker", action="store_true", help="Check circuit breaker"
    )
    group.add_argument(
        "--check-budget", action="store_true", help="Check budget limits"
    )
    group.add_argument("--check-all", metavar="TASK_ID", help="Check all conditions")
    group.add_argument("--reset", action="store_true", help="Reset all state")
    group.add_argument(
        "--analyze-failures", action="store_true", help="Analyze failure patterns"
    )

    parser.add_argument("--error", help="Error message for --record-failure")
    parser.add_argument(
        "--files", nargs="*", help="List of files for --record-failure"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Threshold for stuck/circuit breaker checks",
    )
    parser.add_argument(
        "--max-iterations", type=int, default=50,
        help="Max iterations for budget check"
    )
    parser.add_argument(
        "--timeout-hours", type=int, default=8,
        help="Timeout hours for budget check"
    )
    parser.add_argument("--config", help="JSON config for --check-all")

    args = parser.parse_args()

    mgr = ResilienceManager(args.state_path)
    if os.path.exists(args.state_path):
        mgr.load()

    if args.record_failure:
        mgr.record_failure(args.record_failure, error=args.error, files=args.files)
        sys.exit(0)

    elif args.record_success:
        mgr.record_success(args.record_success)
        sys.exit(0)

    elif args.check_stuck:
        is_stuck, count, msg = mgr.check_stuck(args.check_stuck, args.threshold)
        print(msg)
        sys.exit(1 if is_stuck else 0)

    elif args.check_circuit_breaker:
        is_tripped, count, msg = mgr.check_circuit_breaker(args.threshold)
        print(msg)
        sys.exit(1 if is_tripped else 0)

    elif args.check_budget:
        exceeded, reason, msg = mgr.check_budget(args.max_iterations, args.timeout_hours)
        if msg:
            print(msg)
        sys.exit(1 if exceeded else 0)

    elif args.check_all:
        config = {}
        if args.config:
            config = json.loads(args.config)
        triggered, check_name, msg = mgr.check_all(args.check_all, config)
        if triggered and msg:
            print(msg)
        sys.exit(1 if triggered else 0)

    elif args.reset:
        mgr.reset()
        sys.exit(0)

    elif args.analyze_failures:
        analysis = mgr.analyze_failures()
        print(json.dumps(analysis))
        sys.exit(0)


if __name__ == "__main__":
    main()
