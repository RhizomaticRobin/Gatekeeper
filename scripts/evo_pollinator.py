#!/usr/bin/env python3
"""Cross-task approach pollination for GSD-VGL.

Loads a plan.yaml to find completed tasks, computes file_scope similarity
to a target task, and migrates successful approaches from similar completed
tasks into the target task's evolution database on an inspiration island.

Similarity scoring:
  +3  exact file path match
  +1  shared parent directory (only when no exact match for that file)
  +2  same inferred task type

Only approaches with test_pass_rate >= 0.5 are eligible for migration.
Migrated approaches are placed on the inspiration island (last island,
index num_islands - 1).

Functions:
  pollinate(target_db_path, plan_path, task_id, threshold=0.3)
  _compute_similarity(task_a_scope, task_b_scope)
  _infer_task_type(file_scope)

CLI:
  python3 evo_pollinator.py --pollinate TARGET_DB PLAN_PATH TASK_ID [--threshold 0.3]
"""

import argparse
import json
import os
import sys
import time
import uuid
from collections import Counter

# Ensure scripts/ directory is importable
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from evo_db import Approach, EvolutionDB
from plan_utils import load_plan, find_task


# ---------------------------------------------------------------------------
# Task type inference
# ---------------------------------------------------------------------------

def _infer_task_type(file_scope):
    """Infer the dominant task type from a list of file paths.

    Mapping:
      .py, .sh           -> backend
      .tsx, .jsx          -> frontend
      .test., .spec.      -> test
      everything else     -> general

    Uses majority vote across all files in the scope.

    Args:
        file_scope: list of file path strings, or a dict with a 'file_scope' key.

    Returns:
        str: one of 'backend', 'frontend', 'test', 'general'
    """
    if isinstance(file_scope, dict):
        file_scope = file_scope.get("file_scope", [])
    if not file_scope:
        return "general"

    votes = Counter()
    for fp in file_scope:
        basename = os.path.basename(fp)
        # Check test patterns first (they may also have .py/.tsx extensions)
        if ".test." in fp or ".spec." in fp:
            votes["test"] += 1
        elif fp.endswith(".py") or fp.endswith(".sh"):
            votes["backend"] += 1
        elif fp.endswith(".tsx") or fp.endswith(".jsx"):
            votes["frontend"] += 1
        else:
            votes["general"] += 1

    if not votes:
        return "general"
    return votes.most_common(1)[0][0]


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------

def _compute_similarity(task_a_scope, task_b_scope):
    """Compute a similarity score between two task scopes.

    Both arguments are dicts with a 'file_scope' key containing lists of
    file paths.

    Scoring:
      +3  for each exact file path match between the two scopes
      +1  for each file in scope_b whose parent directory matches a parent
          directory of a file in scope_a (only when no exact match already
          counted for that file)
      +2  if the inferred task types match

    Returns:
        int: similarity score (0 means no overlap)
    """
    raw_a = task_a_scope.get("file_scope", [])
    raw_b = task_b_scope.get("file_scope", [])
    # Unwrap dict-style file_scope ({owns: [...], reads: [...]}) from plan.yaml
    if isinstance(raw_a, dict):
        raw_a = list(raw_a.get("owns", [])) + list(raw_a.get("reads", []))
    if isinstance(raw_b, dict):
        raw_b = list(raw_b.get("owns", [])) + list(raw_b.get("reads", []))
    files_a = set(raw_a)
    files_b = set(raw_b)

    score = 0

    # Exact file path matches
    exact_matches = files_a & files_b
    score += 3 * len(exact_matches)

    # Directory overlap for files that did NOT have an exact match
    dirs_a = set()
    for f in files_a:
        d = os.path.dirname(f)
        if d:
            dirs_a.add(d)

    for f in files_b:
        if f in exact_matches:
            continue
        d = os.path.dirname(f)
        if d and d in dirs_a:
            score += 1

    # Task type match
    type_a = _infer_task_type(task_a_scope)
    type_b = _infer_task_type(task_b_scope)
    if type_a == type_b and type_a != "general":
        score += 2

    return score


# ---------------------------------------------------------------------------
# Pollination
# ---------------------------------------------------------------------------

def pollinate(target_db_path, plan_path, task_id, threshold=0.3):
    """Load plan, find similar completed tasks, migrate top approaches.

    Steps:
      1. Load plan and find the target task.
      2. Gather all completed tasks (excluding the target itself).
      3. Score each completed task's file_scope similarity to the target.
      4. Filter out tasks below the threshold.
      5. Load the EvolutionDB from target_db_path.
      6. For each qualifying source task, find its approaches in the DB.
      7. Only migrate approaches with test_pass_rate >= 0.5.
      8. Migrate copies to the inspiration island (last island).
      9. Save the DB and return summary.

    Args:
        target_db_path: path to the EvolutionDB directory
        plan_path: path to plan.yaml
        task_id: the target task ID (e.g. "1.2")
        threshold: minimum similarity score to consider (default 0.3)

    Returns:
        dict: {"migrated": N, "source_tasks": [...], "target_island": int}
    """
    # Load plan
    plan = load_plan(plan_path)

    # Find target task
    _, target_task = find_task(plan, task_id)
    if target_task is None:
        return {"migrated": 0, "source_tasks": [], "target_island": 0}

    target_scope = {"file_scope": target_task.get("file_scope", [])}

    # Gather completed tasks (not the target itself)
    completed_tasks = []
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            if (
                task.get("status") == "completed"
                and str(task["id"]) != str(task_id)
            ):
                completed_tasks.append(task)

    if not completed_tasks:
        return {"migrated": 0, "source_tasks": [], "target_island": 0}

    # Score similarity for each completed task
    similar_tasks = []
    for task in completed_tasks:
        task_scope = {"file_scope": task.get("file_scope", [])}
        sim_score = _compute_similarity(target_scope, task_scope)
        if sim_score >= threshold:
            similar_tasks.append((sim_score, task))

    # Sort by score descending
    similar_tasks.sort(key=lambda x: x[0], reverse=True)

    if not similar_tasks:
        return {"migrated": 0, "source_tasks": [], "target_island": 0}

    # Load EvolutionDB
    db = EvolutionDB()
    if os.path.exists(os.path.join(target_db_path, "approaches.jsonl")):
        db.load(target_db_path)
    elif os.path.exists(target_db_path):
        # Try loading anyway -- load() handles missing files gracefully
        db.load(target_db_path)

    inspiration_island = db.num_islands - 1

    # If the DB is empty (no approaches), return early
    if not db.approaches:
        return {"migrated": 0, "source_tasks": [], "target_island": inspiration_island}

    # For each similar completed task, find and migrate approaches
    migrated_count = 0
    source_task_ids = []

    for sim_score, task in similar_tasks:
        source_tid = str(task["id"])

        # Find approaches in DB from this source task
        source_approaches = [
            a for a in db.approaches.values()
            if a.task_id == source_tid
        ]

        # Filter: only migrate approaches with test_pass_rate >= 0.5
        eligible = [
            a for a in source_approaches
            if a.metrics.get("test_pass_rate", 0.0) >= 0.5
        ]

        if not eligible:
            continue

        task_migrated = False
        for approach in eligible:
            # Create a copy on the inspiration island
            migrated = Approach(
                id=str(uuid.uuid4()),
                prompt_addendum=approach.prompt_addendum,
                parent_id=approach.id,
                generation=approach.generation + 1,
                metrics=dict(approach.metrics),
                island=inspiration_island,
                feature_coords=(),  # recalculated by add()
                task_id=str(task_id),  # re-assign to target task
                task_type=approach.task_type,
                file_patterns=list(approach.file_patterns),
                artifacts=dict(approach.artifacts),
                timestamp=time.time(),
                iteration=approach.iteration,
            )
            db.add(migrated)
            migrated_count += 1
            task_migrated = True

        if task_migrated:
            source_task_ids.append(source_tid)

    # Save the DB
    db.save(target_db_path)

    return {
        "migrated": migrated_count,
        "source_tasks": source_task_ids,
        "target_island": inspiration_island,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GSD-VGL Cross-Task Approach Pollinator"
    )
    parser.add_argument(
        "--pollinate",
        nargs=3,
        metavar=("TARGET_DB", "PLAN_PATH", "TASK_ID"),
        help="Pollinate approaches from similar completed tasks",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        help="Minimum similarity score threshold (default: 0.3)",
    )

    args = parser.parse_args()

    if args.pollinate:
        target_db, plan_path, task_id = args.pollinate
        result = pollinate(target_db, plan_path, task_id, threshold=args.threshold)
        print(json.dumps(result))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
