#!/usr/bin/env python3
"""Dynamic wave sizer for GSD-VGL concurrent task execution.

Computes the recommended wave size (number of tasks to run in parallel)
based on task scope (number of owned files), historical execution duration,
and an upper-bound concurrency limit.

Functions:
  compute_wave_size(tasks, history=None, max_concurrent=4)
      -- returns an integer wave size in [1, max_concurrent]

Heuristics:
  1. Start with min(len(tasks), max_concurrent) as the baseline.
  2. If average file scope across tasks >= 20 files, apply a scope penalty
     that reduces the wave size proportionally.
  3. If historical average duration >= 120 seconds, apply a duration penalty
     that reduces the wave size proportionally.
  4. The result is always clamped to [1, max_concurrent].

CLI:
  python3 wave_sizer.py plan.yaml [--max-concurrent 4]
  Outputs JSON: {"wave_size": N, "reasoning": "..."}
"""

import argparse
import json
import math
import os
import sys

import yaml


# ---------------------------------------------------------------------------
# Thresholds (tunable)
# ---------------------------------------------------------------------------

_LARGE_SCOPE_THRESHOLD = 20   # avg owned_files count that triggers penalty
_SLOW_DURATION_THRESHOLD = 120.0  # avg duration_s that triggers penalty


def compute_wave_size(tasks, history=None, max_concurrent=4):
    """Compute the recommended wave size for a set of tasks.

    Args:
        tasks: list of task dicts, each may contain an 'owned_files' list.
        history: optional list of history record dicts with 'duration_s' keys.
        max_concurrent: upper bound on concurrency (default 4).

    Returns:
        int -- recommended wave size in [1, max_concurrent].
    """
    if not tasks:
        return 0

    task_count = len(tasks)

    # Baseline: min of task count and max_concurrent
    baseline = min(task_count, max_concurrent)

    # --- Scope penalty -------------------------------------------------------
    # Average number of owned files across all tasks
    total_files = 0
    for t in tasks:
        owned = t.get("owned_files") or []
        total_files += len(owned)
    avg_scope = total_files / task_count if task_count > 0 else 0

    scope_factor = 1.0
    if avg_scope >= _LARGE_SCOPE_THRESHOLD:
        # Linear reduction: at 20 files -> factor ~0.5, at 40 files -> ~0.25
        # Formula: factor = threshold / (threshold + (avg_scope - threshold))
        overshoot = avg_scope - _LARGE_SCOPE_THRESHOLD
        scope_factor = _LARGE_SCOPE_THRESHOLD / (_LARGE_SCOPE_THRESHOLD + overshoot * 2)
        scope_factor = max(scope_factor, 0.25)  # floor at 25%

    # --- History / duration penalty ------------------------------------------
    duration_factor = 1.0
    if history:
        durations = [h.get("duration_s", 0) for h in history if h.get("duration_s")]
        if durations:
            avg_duration = sum(durations) / len(durations)
            if avg_duration >= _SLOW_DURATION_THRESHOLD:
                overshoot = avg_duration - _SLOW_DURATION_THRESHOLD
                duration_factor = _SLOW_DURATION_THRESHOLD / (
                    _SLOW_DURATION_THRESHOLD + overshoot
                )
                duration_factor = max(duration_factor, 0.25)

    # --- Combine factors -----------------------------------------------------
    combined_factor = scope_factor * duration_factor
    wave_size = baseline * combined_factor

    # Clamp to [1, max_concurrent]
    wave_size = max(1, min(max_concurrent, int(math.ceil(wave_size))))

    # Special case: single task always returns 1
    if task_count == 1:
        wave_size = 1

    return wave_size


def _build_reasoning(task_count, avg_scope, avg_duration, scope_factor,
                     duration_factor, wave_size, max_concurrent):
    """Build a human-readable reasoning string."""
    parts = []
    parts.append(f"{task_count} tasks considered")

    if avg_scope >= _LARGE_SCOPE_THRESHOLD:
        parts.append(
            f"avg file scope is {avg_scope:.1f} (>={_LARGE_SCOPE_THRESHOLD}), "
            f"reducing by scope factor {scope_factor:.2f}"
        )
    else:
        parts.append(f"avg file scope is {avg_scope:.1f} (below threshold)")

    if avg_duration >= _SLOW_DURATION_THRESHOLD:
        parts.append(
            f"avg historical duration is {avg_duration:.1f}s "
            f"(>={_SLOW_DURATION_THRESHOLD}s), "
            f"reducing by duration factor {duration_factor:.2f}"
        )
    elif avg_duration > 0:
        parts.append(f"avg historical duration is {avg_duration:.1f}s (fast)")
    else:
        parts.append("no historical duration data")

    parts.append(f"max_concurrent={max_concurrent}")
    parts.append(f"recommended wave_size={wave_size}")

    return "; ".join(parts)


def main():
    """CLI entry point.

    Usage: python3 wave_sizer.py plan.yaml [--max-concurrent 4]
    Output: JSON object with wave_size and reasoning.
    """
    parser = argparse.ArgumentParser(
        description="Compute recommended wave size for parallel task execution"
    )
    parser.add_argument(
        "plan_file",
        help="Path to plan.yaml"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=4,
        help="Maximum concurrency (default: 4)"
    )
    parser.add_argument(
        "--history-dir",
        default=None,
        help="Override history directory for historical data"
    )

    args = parser.parse_args()

    # Load the plan
    with open(args.plan_file, "r") as f:
        plan = yaml.safe_load(f)

    # Collect all tasks from all phases
    tasks = []
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            tasks.append(task)

    # Load history if available
    history = None
    if args.history_dir:
        history_path = os.path.join(args.history_dir, "runs.jsonl")
        if os.path.exists(history_path):
            history = []
            with open(history_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        history.append(json.loads(line))

    wave_size = compute_wave_size(
        tasks, history=history, max_concurrent=args.max_concurrent
    )

    # Compute reasoning details
    task_count = len(tasks)
    total_files = sum(len(t.get("owned_files", [])) for t in tasks)
    avg_scope = total_files / task_count if task_count > 0 else 0

    avg_duration = 0.0
    if history:
        durations = [h.get("duration_s", 0) for h in history if h.get("duration_s")]
        if durations:
            avg_duration = sum(durations) / len(durations)

    scope_factor = 1.0
    if avg_scope >= _LARGE_SCOPE_THRESHOLD:
        overshoot = avg_scope - _LARGE_SCOPE_THRESHOLD
        scope_factor = _LARGE_SCOPE_THRESHOLD / (_LARGE_SCOPE_THRESHOLD + overshoot * 2)
        scope_factor = max(scope_factor, 0.25)

    duration_factor = 1.0
    if avg_duration >= _SLOW_DURATION_THRESHOLD:
        overshoot = avg_duration - _SLOW_DURATION_THRESHOLD
        duration_factor = _SLOW_DURATION_THRESHOLD / (
            _SLOW_DURATION_THRESHOLD + overshoot
        )
        duration_factor = max(duration_factor, 0.25)

    reasoning = _build_reasoning(
        task_count, avg_scope, avg_duration, scope_factor,
        duration_factor, wave_size, args.max_concurrent
    )

    output = {
        "wave_size": wave_size,
        "reasoning": reasoning,
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
