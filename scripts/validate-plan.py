#!/usr/bin/env python3
"""Validate a GSD-VGL plan.yaml file.

Exit 0 = valid, Exit 1 = errors found.
Errors go to stderr, summary to stdout.

Usage:
  python3 validate-plan.py <plan.yaml>
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plan_utils import load_plan, get_all_task_ids, topological_sort

VALID_STATUSES = {"pending", "in_progress", "completed"}

REQUIRED_METADATA = ["project", "dev_server_command", "dev_server_url"]

REQUIRED_TASK_FIELDS = ["id", "name", "status", "depends_on"]


def validate(path):
    errors = []
    warnings = []

    # 1. Parse YAML
    try:
        plan = load_plan(path)
    except Exception as e:
        print(f"YAML parse error: {e}", file=sys.stderr)
        return 1

    if not isinstance(plan, dict):
        print("Error: plan.yaml root must be a mapping", file=sys.stderr)
        return 1

    # 2. Required metadata fields
    metadata = plan.get("metadata", {})
    if not isinstance(metadata, dict):
        errors.append("metadata must be a mapping")
    else:
        for field in REQUIRED_METADATA:
            if not metadata.get(field):
                errors.append(f"metadata.{field} is required")
        # Optional but recommended metadata
        if not metadata.get("model_profile"):
            warnings.append("metadata.model_profile not set (will use 'default')")
        if not metadata.get("test_framework"):
            warnings.append("metadata.test_framework not set")

    # 3. Phases exist
    phases = plan.get("phases", [])
    if not isinstance(phases, list) or len(phases) == 0:
        errors.append("phases must be a non-empty list")
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        return 1

    # 4. Collect all task IDs for dep checking
    all_ids = set()
    all_tasks = []
    for phase in phases:
        if not isinstance(phase, dict):
            errors.append("Each phase must be a mapping")
            continue
        if not phase.get("id"):
            errors.append("Each phase must have an 'id' field")
        if not phase.get("name"):
            errors.append(f"Phase {phase.get('id', '?')} must have a 'name' field")

        # Phase-level must_haves validation
        phase_mh = phase.get("must_haves")
        if phase_mh is not None:
            if not isinstance(phase_mh, dict):
                errors.append(f"Phase {phase.get('id', '?')}: must_haves must be a mapping")
            else:
                for key in ("truths", "artifacts", "key_links"):
                    val = phase_mh.get(key)
                    if val is not None and not isinstance(val, list):
                        errors.append(f"Phase {phase.get('id', '?')}: must_haves.{key} must be a list")

        tasks = phase.get("tasks", [])
        if not isinstance(tasks, list):
            errors.append(f"Phase {phase.get('id', '?')}: tasks must be a list")
            continue
        for task in tasks:
            if not isinstance(task, dict):
                errors.append("Each task must be a mapping")
                continue
            all_tasks.append(task)
            tid = str(task.get("id", ""))
            if tid:
                if tid in all_ids:
                    errors.append(f"Duplicate task ID: {tid}")
                all_ids.add(tid)

    # 5. Validate each task
    for task in all_tasks:
        tid = str(task.get("id", "?"))
        prefix = f"Task {tid}"

        # Required top-level fields
        for field in REQUIRED_TASK_FIELDS:
            if field not in task:
                errors.append(f"{prefix}: missing required field '{field}'")

        # Status enum
        status = task.get("status", "")
        if status not in VALID_STATUSES:
            errors.append(f"{prefix}: invalid status '{status}' (must be one of {VALID_STATUSES})")

        # depends_on references
        deps = task.get("depends_on", [])
        if not isinstance(deps, list):
            errors.append(f"{prefix}: depends_on must be a list")
        else:
            for dep in deps:
                if str(dep) not in all_ids:
                    errors.append(f"{prefix}: depends_on references unknown task '{dep}'")

        # Deliverables
        deliverables = task.get("deliverables", {})
        if not isinstance(deliverables, dict):
            errors.append(f"{prefix}: deliverables must be a mapping")
        else:
            if not deliverables.get("backend"):
                errors.append(f"{prefix}: deliverables.backend is required")
            if not deliverables.get("frontend"):
                errors.append(f"{prefix}: deliverables.frontend is required")

        # Tests
        tests = task.get("tests", {})
        if not isinstance(tests, dict):
            errors.append(f"{prefix}: tests must be a mapping")
        else:
            quant = tests.get("quantitative", {})
            if not isinstance(quant, dict) or not quant.get("command"):
                errors.append(f"{prefix}: tests.quantitative.command is required")

            qual = tests.get("qualitative", {})
            if not isinstance(qual, dict):
                errors.append(f"{prefix}: tests.qualitative must be a mapping")
            else:
                criteria = qual.get("criteria", [])
                if not isinstance(criteria, list) or len(criteria) == 0:
                    errors.append(f"{prefix}: tests.qualitative.criteria is required (non-empty list)")

        # Prompt file
        if not task.get("prompt_file"):
            errors.append(f"{prefix}: prompt_file is required")

        # must_haves validation (extended for GSD-VGL)
        task_mh = task.get("must_haves")
        if task_mh is not None:
            if not isinstance(task_mh, dict):
                errors.append(f"{prefix}: must_haves must be a mapping")
            else:
                for key in ("truths", "artifacts", "key_links"):
                    val = task_mh.get(key)
                    if val is not None and not isinstance(val, list):
                        errors.append(f"{prefix}: must_haves.{key} must be a list")

        # wave validation
        wave = task.get("wave")
        if wave is not None:
            if not isinstance(wave, int) or wave < 1:
                errors.append(f"{prefix}: wave must be a positive integer")

        # file_scope validation
        file_scope = task.get("file_scope")
        if file_scope is not None:
            if not isinstance(file_scope, dict):
                errors.append(f"{prefix}: file_scope must be a mapping")
            else:
                owns = file_scope.get("owns")
                if owns is not None:
                    if not isinstance(owns, list) or not all(isinstance(p, str) for p in owns):
                        errors.append(f"{prefix}: file_scope.owns must be a list of strings")
                reads = file_scope.get("reads")
                if reads is not None:
                    if not isinstance(reads, list) or not all(isinstance(p, str) for p in reads):
                        errors.append(f"{prefix}: file_scope.reads must be a list of strings")

    # 5b. Warn about overlapping file_scope.owns between independent tasks
    scope_map = {}
    for task in all_tasks:
        tid = str(task.get("id", ""))
        scope = task.get("file_scope")
        if scope and isinstance(scope, dict):
            owns = scope.get("owns", [])
            if isinstance(owns, list):
                scope_map[tid] = owns
    dep_map = {}
    for task in all_tasks:
        tid = str(task.get("id", ""))
        dep_map[tid] = set(str(d) for d in task.get("depends_on", []))

    scoped_ids = list(scope_map.keys())
    for i in range(len(scoped_ids)):
        for j in range(i + 1, len(scoped_ids)):
            a, b = scoped_ids[i], scoped_ids[j]
            if a in dep_map.get(b, set()) or b in dep_map.get(a, set()):
                continue
            for pa in scope_map[a]:
                for pb in scope_map[b]:
                    norm_a = pa.rstrip("/") + "/"
                    norm_b = pb.rstrip("/") + "/"
                    if norm_a.startswith(norm_b) or norm_b.startswith(norm_a) or pa == pb:
                        print(f"Warning: Tasks {a} and {b} have overlapping file_scope.owns: {pa} vs {pb}",
                              file=sys.stderr)

    # 6. Cycle detection
    if len(all_ids) > 0:
        try:
            _, has_cycle = topological_sort(plan)
            if has_cycle:
                errors.append("Dependency cycle detected in task graph")
        except Exception as e:
            errors.append(f"Cycle detection failed: {e}")

    # Output results
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        print(f"Validation FAILED: {len(errors)} error(s) found")
        return 1
    else:
        task_count = len(all_tasks)
        phase_count = len(phases)
        print(f"Validation PASSED: {phase_count} phase(s), {task_count} task(s)")
        return 0


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 validate-plan.py <plan.yaml>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    sys.exit(validate(path))


if __name__ == "__main__":
    main()
