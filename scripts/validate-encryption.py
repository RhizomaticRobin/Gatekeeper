#!/usr/bin/env python3
"""Validate encryption plan before encrypting task files.

Checks that encrypting task specs and skeleton files won't break the workflow:
1. Read-dependency safety — concurrent tasks can read what they need
2. Wave-concurrent reads — same-wave tasks don't lock each other out
3. Shared files — files read by multiple tasks are marked safe to skip

Usage:
  python3 validate-encryption.py <plan.yaml>

Output:
  JSON with safe_to_encrypt, skip_encryption, skip_reasons, verdict
"""

import sys
import os
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_utils import load_plan


def _get_transitive_deps(task_id, dep_map, cache=None):
    """Get all transitive dependencies for a task."""
    if cache is None:
        cache = {}
    if task_id in cache:
        return cache[task_id]
    direct = dep_map.get(task_id, set())
    transitive = set(direct)
    for dep in direct:
        transitive |= _get_transitive_deps(dep, dep_map, cache)
    cache[task_id] = transitive
    return transitive


def validate_encryption_plan(plan):
    """Validate that encrypting task files won't break the workflow.

    Returns:
        dict with safe_to_encrypt, skip_encryption, skip_reasons, issues, verdict
    """
    issues = []
    skip_encryption = {}
    safe_to_encrypt = []

    # Build task maps
    all_tasks = []
    dep_map = {}       # task_id -> set of direct dependency task_ids
    owns_map = {}      # task_id -> list of owned file paths
    reads_map = {}     # task_id -> list of read file paths
    wave_map = {}      # task_id -> wave number
    file_owner = {}    # file_path -> task_id that owns it
    file_readers = defaultdict(set)  # file_path -> set of task_ids that read it

    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            tid = str(task.get("id", ""))
            all_tasks.append(tid)
            dep_map[tid] = set(str(d) for d in task.get("depends_on", []))
            scope = task.get("file_scope", {})
            if isinstance(scope, dict):
                owns_map[tid] = [p for p in scope.get("owns", []) if isinstance(p, str)]
                reads_map[tid] = [p for p in scope.get("reads", []) if isinstance(p, str)]
            else:
                owns_map[tid] = []
                reads_map[tid] = []
            wave_map[tid] = task.get("wave", 1)

            for owned in owns_map[tid]:
                file_owner[owned] = tid

            for read_path in reads_map[tid]:
                file_readers[read_path].add(tid)

    # Compute transitive deps
    trans_cache = {}
    for tid in all_tasks:
        _get_transitive_deps(tid, dep_map, trans_cache)

    # Check 1: Read-dependency safety
    for tid in all_tasks:
        trans_deps = trans_cache.get(tid, set())
        for read_path in reads_map[tid]:
            owner = file_owner.get(read_path)
            if owner and owner != tid and owner not in trans_deps:
                # This task reads a file owned by a non-dependency task
                # Encrypting the owner's file would lock this task out
                skip_encryption[read_path] = (
                    f"read by task {tid} but owned by task {owner} "
                    f"(no dependency chain: {tid} does not depend on {owner})"
                )

    # Check 2: Wave-concurrent reads
    for tid in all_tasks:
        for read_path in reads_map[tid]:
            owner = file_owner.get(read_path)
            if owner and owner != tid and wave_map.get(owner) == wave_map.get(tid):
                skip_encryption[read_path] = (
                    f"read by task {tid} (wave {wave_map[tid]}) but owned by "
                    f"task {owner} (same wave) — concurrent tasks can't wait for each other"
                )

    # Check 3: Shared files (read by multiple tasks)
    for file_path, readers in file_readers.items():
        if len(readers) > 1:
            owner = file_owner.get(file_path)
            if owner:
                # Multiple tasks read this file — check if they all depend on the owner
                for reader in readers:
                    if reader == owner:
                        continue
                    if owner not in trans_cache.get(reader, set()):
                        skip_encryption[file_path] = (
                            f"shared file read by {len(readers)} tasks "
                            f"({', '.join(sorted(readers))}), "
                            f"not all depend on owner {owner}"
                        )
                        break

    # Build safe_to_encrypt list (everything NOT in skip_encryption)
    for tid in all_tasks:
        # Task spec file is always safe to encrypt (dependency-gated by design)
        prompt_file = None
        for phase in plan.get("phases", []):
            for task in phase.get("tasks", []):
                if str(task.get("id", "")) == tid:
                    prompt_file = task.get("prompt_file", "")
        if prompt_file:
            safe_to_encrypt.append(f".claude/plan/{prompt_file}")

        # Owned skeleton files — only if not in skip list
        for owned in owns_map[tid]:
            if owned not in skip_encryption:
                safe_to_encrypt.append(owned)

    verdict = "SAFE" if not issues else "UNSAFE"

    return {
        "safe_to_encrypt": sorted(safe_to_encrypt),
        "skip_encryption": sorted(skip_encryption.keys()),
        "skip_reasons": skip_encryption,
        "issues": issues,
        "verdict": verdict,
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 validate-encryption.py <plan.yaml>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    plan = load_plan(path)
    result = validate_encryption_plan(plan)

    print(json.dumps(result, indent=2))

    n_safe = len(result["safe_to_encrypt"])
    n_skip = len(result["skip_encryption"])
    print(f"\n{n_safe} files safe to encrypt, {n_skip} files skipped", file=sys.stderr)

    if result["skip_encryption"]:
        print("Skipped files:", file=sys.stderr)
        for path, reason in result["skip_reasons"].items():
            print(f"  {path}: {reason}", file=sys.stderr)


if __name__ == "__main__":
    main()
