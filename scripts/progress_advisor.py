#!/usr/bin/env python3
"""Progress-aware decision making for GSD-VGL task execution.

Computes project progress, identifies the critical path through the task
dependency DAG, and provides prioritization advice that adapts based on
completion percentage.

Functions:
  compute_progress(plan) -- percentage of completed tasks (0.0 to 100.0)
  find_critical_path(plan) -- longest path in the dependency DAG
  advise(plan, history=None) -- return prioritization recommendations

When progress exceeds 70%, advice shifts to focus on remaining blockers
and deprioritize non-blocking tasks.

CLI:
  python3 progress_advisor.py plan.yaml
  Outputs JSON: {"progress": N, "critical_path": [...], "advice": "..."}
"""

import argparse
import json
import sys
from collections import defaultdict, deque

try:
    import yaml
except ImportError:
    yaml = None


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _collect_tasks(plan):
    """Collect all tasks from all phases in the plan.

    Returns:
        list of task dicts
    """
    tasks = []
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            tasks.append(task)
    return tasks


def compute_progress(plan):
    """Compute the percentage of completed tasks.

    Args:
        plan: plan dict with phases and tasks

    Returns:
        float -- percentage from 0.0 to 100.0
    """
    tasks = _collect_tasks(plan)
    total = len(tasks)
    if total == 0:
        return 0.0

    completed = sum(1 for t in tasks if t.get("status") == "completed")
    return round((completed / total) * 100, 2)


def find_critical_path(plan):
    """Find the longest path in the task dependency DAG.

    Uses topological ordering and dynamic programming to find the longest
    path (critical path) through the dependency graph.

    Args:
        plan: plan dict with phases and tasks

    Returns:
        list of task ID strings representing the critical path, ordered
        from the earliest dependency to the latest dependent task.
        Returns [] for an empty plan.
    """
    tasks = _collect_tasks(plan)
    if not tasks:
        return []

    # Build adjacency and reverse-adjacency structures
    task_ids = set()
    deps_map = {}  # task_id -> list of dependency task_ids
    children_map = defaultdict(list)  # task_id -> list of dependent task_ids

    for t in tasks:
        tid = str(t["id"])
        task_ids.add(tid)
        task_deps = [str(d) for d in t.get("depends_on", [])]
        deps_map[tid] = task_deps

    # Build forward adjacency: dep -> dependent
    for tid, dep_list in deps_map.items():
        for dep in dep_list:
            if dep in task_ids:
                children_map[dep].append(tid)

    # Topological sort (Kahn's algorithm)
    in_degree = {tid: 0 for tid in task_ids}
    for tid, dep_list in deps_map.items():
        for dep in dep_list:
            if dep in task_ids:
                in_degree[tid] += 1

    queue = deque([tid for tid in task_ids if in_degree[tid] == 0])
    topo_order = []

    while queue:
        node = queue.popleft()
        topo_order.append(node)
        for child in children_map[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Dynamic programming: longest path from any root
    # dist[tid] = length of longest path ending at tid
    dist = {tid: 1 for tid in task_ids}
    predecessor = {tid: None for tid in task_ids}

    for node in topo_order:
        for child in children_map[node]:
            if dist[node] + 1 > dist[child]:
                dist[child] = dist[node] + 1
                predecessor[child] = node

    # Find the node with the maximum distance
    if not dist:
        return []

    end_node = max(dist, key=dist.get)

    # Reconstruct path
    path = []
    current = end_node
    while current is not None:
        path.append(current)
        current = predecessor[current]

    path.reverse()
    return path


def _find_remaining_blockers(plan):
    """Find pending tasks that block other pending tasks.

    Returns:
        list of task ID strings that are blockers (i.e., other pending
        tasks depend on them).
    """
    tasks = _collect_tasks(plan)
    pending_ids = set()
    blocked_by = set()

    for t in tasks:
        tid = str(t["id"])
        if t.get("status") != "completed":
            pending_ids.add(tid)

    for t in tasks:
        if t.get("status") != "completed":
            for dep in t.get("depends_on", []):
                dep_str = str(dep)
                if dep_str in pending_ids:
                    blocked_by.add(dep_str)

    return sorted(blocked_by)


def advise(plan, history=None):
    """Return prioritization recommendations based on progress.

    When progress < 70%: standard prioritization based on critical path.
    When progress >= 70%: focus on remaining blockers, deprioritize
        non-blocking tasks.
    When progress == 100%: completion message.

    Args:
        plan: plan dict with phases and tasks
        history: optional list of history records (reserved for future use)

    Returns:
        dict with keys:
            progress: float (0.0 - 100.0)
            critical_path: list of task ID strings
            advice: string with prioritization recommendation
    """
    progress = compute_progress(plan)
    critical_path = find_critical_path(plan)

    if progress == 100.0:
        advice_text = (
            "All tasks complete. The project is finished. "
            "Review deliverables and run final verification."
        )
    elif progress >= 70.0:
        blockers = _find_remaining_blockers(plan)
        tasks = _collect_tasks(plan)
        remaining = [str(t["id"]) for t in tasks if t.get("status") != "completed"]
        non_blocking = [tid for tid in remaining if tid not in blockers]

        advice_parts = [
            f"Progress is {progress}% (>70%): focus on remaining blockers.",
        ]
        if blockers:
            advice_parts.append(
                f"Blocker tasks to prioritize: {', '.join(blockers)}."
            )
        if non_blocking:
            advice_parts.append(
                f"Non-blocking tasks to deprioritize: {', '.join(non_blocking)}."
            )
        if not blockers and remaining:
            advice_parts.append(
                "No remaining blockers found. Complete remaining tasks in any order."
            )
        advice_text = " ".join(advice_parts)
    else:
        # Early stage: standard prioritization
        advice_parts = [
            f"Progress is {progress}% (<70%): follow standard prioritization.",
        ]
        if critical_path:
            advice_parts.append(
                f"Critical path: {' -> '.join(critical_path)} "
                f"(length {len(critical_path)})."
            )
            advice_parts.append(
                "Prioritize tasks on the critical path to avoid delays."
            )
        else:
            advice_parts.append(
                "No dependency chain found. Tasks can be executed in any order."
            )
        advice_text = " ".join(advice_parts)

    return {
        "progress": progress,
        "critical_path": critical_path,
        "advice": advice_text,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point.

    Usage: python3 progress_advisor.py plan.yaml
    Output: JSON object with progress, critical_path, and advice.
    """
    parser = argparse.ArgumentParser(
        description="GSD-VGL Progress-Aware Decision Making"
    )
    parser.add_argument(
        "plan_file",
        help="Path to plan.yaml"
    )

    args = parser.parse_args()

    # Load the plan
    if yaml is None:
        print(json.dumps({"error": "PyYAML is required. Install with: pip install pyyaml"}))
        sys.exit(1)

    with open(args.plan_file, "r") as f:
        plan = yaml.safe_load(f)

    result = advise(plan)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
