#!/usr/bin/env python3
"""Compute parallelizable phase waves from a high-level plan outline.

Uses Kahn's algorithm at the phase level to group phases into waves.
Phases in the same wave have no dependencies on each other and can
be planned in parallel.

Usage:
  python3 phase_waves.py <outline.yaml>

Output:
  JSON array of waves, each wave is a list of phase IDs.
  Example: [[1], [2, 3], [4]]  — phase 1 alone, then 2+3 parallel, then 4.
"""

import sys
import os
import json
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_utils import load_plan


def compute_phase_waves(plan_or_outline):
    """Group phases into parallelizable waves using topological sort.

    Args:
        plan_or_outline: Parsed YAML with 'phases' key. Each phase has
                         'id' and 'dependencies' (list of phase IDs).

    Returns:
        List of waves. Each wave is a sorted list of phase IDs that can
        run in parallel. Returns (waves, has_cycle) tuple.
    """
    phases = plan_or_outline.get("phases", [])
    if not phases:
        return [], False

    phase_ids = [p["id"] for p in phases]
    deps = {p["id"]: set(p.get("dependencies", [])) for p in phases}

    # Build adjacency and in-degree
    in_degree = {pid: 0 for pid in phase_ids}
    adjacency = {pid: [] for pid in phase_ids}
    for pid in phase_ids:
        for dep in deps[pid]:
            if dep in adjacency:
                adjacency[dep].append(pid)
                in_degree[pid] += 1

    # Kahn's algorithm — group by waves
    waves = []
    queue = deque(sorted(pid for pid in phase_ids if in_degree[pid] == 0))
    processed = 0

    while queue:
        wave = sorted(queue)
        waves.append(wave)
        next_queue = deque()

        for pid in wave:
            processed += 1
            for neighbor in adjacency[pid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    next_queue.append(neighbor)

        queue = deque(sorted(next_queue))

    has_cycle = processed < len(phase_ids)
    return waves, has_cycle


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 phase_waves.py <outline_or_plan.yaml>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    data = load_plan(path)
    waves, has_cycle = compute_phase_waves(data)

    if has_cycle:
        print("Error: cycle detected in phase dependencies", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(waves))


if __name__ == "__main__":
    main()
