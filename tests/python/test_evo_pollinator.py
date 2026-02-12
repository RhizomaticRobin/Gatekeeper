"""Tests for scripts/evo_pollinator.py -- Cross-task approach pollination."""

import json
import os
import time
import uuid

import pytest
import yaml

# conftest.py ensures scripts/ is on sys.path
from evo_db import Approach, EvolutionDB
from evo_pollinator import pollinate, _compute_similarity, _infer_task_type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_approach(
    island=0,
    test_pass_rate=0.8,
    complexity=5.0,
    generation=0,
    task_id="1.1",
    task_type="backend",
    file_patterns=None,
    prompt_addendum="Try a modular approach",
    parent_id=None,
    iteration=0,
):
    """Create an Approach with sensible defaults for testing."""
    if file_patterns is None:
        file_patterns = ["scripts/evo_db.py"]
    return Approach(
        id=str(uuid.uuid4()),
        prompt_addendum=prompt_addendum,
        parent_id=parent_id,
        generation=generation,
        metrics={"test_pass_rate": test_pass_rate, "complexity": complexity},
        island=island,
        feature_coords=(),
        task_id=task_id,
        task_type=task_type,
        file_patterns=file_patterns,
        artifacts={},
        timestamp=time.time(),
        iteration=iteration,
    )


def _write_plan(tmp_path, tasks):
    """Write a plan.yaml with the given task list and return its path.

    Each task dict should have at least: id, name, status, file_scope.
    """
    phases = [
        {
            "id": 1,
            "name": "Phase 1",
            "tasks": tasks,
        }
    ]
    plan = {
        "metadata": {"project": "test-pollinator"},
        "phases": phases,
    }
    plan_path = tmp_path / "plan.yaml"
    with open(plan_path, "w") as f:
        yaml.dump(plan, f, default_flow_style=False)
    return str(plan_path)


def _create_db_with_approaches(tmp_path, approaches, num_islands=3):
    """Create a saved EvolutionDB and return its directory path."""
    db_dir = str(tmp_path / "evo_db")
    db = EvolutionDB(config={"num_islands": num_islands})
    for a in approaches:
        db.add(a)
    db.save(db_dir)
    return db_dir


# ---------------------------------------------------------------------------
# T1  test_similarity_exact_file_match
# ---------------------------------------------------------------------------

class TestSimilarityExactFileMatch:
    def test_similarity_exact_file_match(self):
        """Exact file path match scores +3."""
        scope_a = {"file_scope": ["scripts/evo_db.py", "scripts/plan_utils.py"]}
        scope_b = {"file_scope": ["scripts/evo_db.py", "tests/test_foo.py"]}
        score = _compute_similarity(scope_a, scope_b)
        # One exact match (scripts/evo_db.py) => +3
        assert score >= 3


# ---------------------------------------------------------------------------
# T2  test_similarity_shared_directory
# ---------------------------------------------------------------------------

class TestSimilaritySharedDirectory:
    def test_similarity_shared_directory(self):
        """Shared parent directory scores +1."""
        scope_a = {"file_scope": ["scripts/evo_db.py"]}
        scope_b = {"file_scope": ["scripts/learnings.py"]}
        score = _compute_similarity(scope_a, scope_b)
        # No exact match but shared directory scripts/ => +1
        assert score >= 1


# ---------------------------------------------------------------------------
# T3  test_similarity_task_type_match
# ---------------------------------------------------------------------------

class TestSimilarityTaskTypeMatch:
    def test_similarity_task_type_match(self):
        """Same inferred task type adds +2."""
        scope_a = {"file_scope": ["scripts/evo_db.py"]}
        scope_b = {"file_scope": ["scripts/learnings.py"]}
        score = _compute_similarity(scope_a, scope_b)
        # Both are .py -> backend, so task_type match => +2
        # Plus shared directory scripts/ => +1
        assert score >= 3  # at least +1 dir + +2 type


# ---------------------------------------------------------------------------
# T4  test_similarity_no_overlap
# ---------------------------------------------------------------------------

class TestSimilarityNoOverlap:
    def test_similarity_no_overlap(self):
        """Completely disjoint scopes score 0."""
        scope_a = {"file_scope": ["frontend/app.tsx"]}
        scope_b = {"file_scope": ["scripts/evo_db.py"]}
        score = _compute_similarity(scope_a, scope_b)
        # No file match, no directory match, different types (frontend vs backend)
        assert score == 0


# ---------------------------------------------------------------------------
# T5  test_pollinate_imports_from_similar
# ---------------------------------------------------------------------------

class TestPollinateImportsFromSimilar:
    def test_pollinate_imports_from_similar(self, tmp_path):
        """pollinate() imports approaches from completed tasks with similar file_scope."""
        # Completed task 1.1 has approaches with good scores
        approaches = [
            _make_approach(
                island=0, task_id="1.1", test_pass_rate=0.9,
                file_patterns=["scripts/evo_db.py"],
                task_type="backend",
            ),
        ]
        db_dir = _create_db_with_approaches(tmp_path, approaches)

        # Plan: task 1.1 completed, task 1.2 pending (target) -- same file scope
        plan_path = _write_plan(tmp_path, [
            {
                "id": "1.1", "name": "Evo DB", "status": "completed",
                "depends_on": [],
                "file_scope": ["scripts/evo_db.py", "scripts/plan_utils.py"],
            },
            {
                "id": "1.2", "name": "Evo Pollinator", "status": "pending",
                "depends_on": ["1.1"],
                "file_scope": ["scripts/evo_pollinator.py", "scripts/plan_utils.py"],
            },
        ])

        result = pollinate(db_dir, plan_path, "1.2", threshold=0.1)
        assert result["migrated"] >= 1
        assert "1.1" in result["source_tasks"]


# ---------------------------------------------------------------------------
# T6  test_pollinate_skips_dissimilar
# ---------------------------------------------------------------------------

class TestPollinateSkipsDissimilar:
    def test_pollinate_skips_dissimilar(self, tmp_path):
        """pollinate() skips completed tasks with no file_scope overlap."""
        approaches = [
            _make_approach(
                island=0, task_id="1.1", test_pass_rate=0.9,
                file_patterns=["frontend/app.tsx"],
                task_type="frontend",
            ),
        ]
        db_dir = _create_db_with_approaches(tmp_path, approaches)

        plan_path = _write_plan(tmp_path, [
            {
                "id": "1.1", "name": "Frontend", "status": "completed",
                "depends_on": [],
                "file_scope": ["frontend/app.tsx"],
            },
            {
                "id": "1.2", "name": "Backend", "status": "pending",
                "depends_on": [],
                "file_scope": ["scripts/something.py"],
            },
        ])

        result = pollinate(db_dir, plan_path, "1.2", threshold=0.3)
        assert result["migrated"] == 0
        assert result["source_tasks"] == []


# ---------------------------------------------------------------------------
# T7  test_pollinate_filters_low_score
# ---------------------------------------------------------------------------

class TestPollinateFiltersLowScore:
    def test_pollinate_filters_low_score(self, tmp_path):
        """Approaches with test_pass_rate < 0.5 are not migrated."""
        approaches = [
            _make_approach(
                island=0, task_id="1.1", test_pass_rate=0.3,
                file_patterns=["scripts/evo_db.py"],
                task_type="backend",
            ),
        ]
        db_dir = _create_db_with_approaches(tmp_path, approaches)

        plan_path = _write_plan(tmp_path, [
            {
                "id": "1.1", "name": "Evo DB", "status": "completed",
                "depends_on": [],
                "file_scope": ["scripts/evo_db.py"],
            },
            {
                "id": "1.2", "name": "Evo Pollinator", "status": "pending",
                "depends_on": [],
                "file_scope": ["scripts/evo_db.py"],
            },
        ])

        result = pollinate(db_dir, plan_path, "1.2", threshold=0.1)
        # Even though similarity is high, approach test_pass_rate=0.3 < 0.5
        assert result["migrated"] == 0


# ---------------------------------------------------------------------------
# T8  test_pollinate_inspiration_island
# ---------------------------------------------------------------------------

class TestPollinateInspirationIsland:
    def test_pollinate_inspiration_island(self, tmp_path):
        """Migrated approaches are placed on the last island (inspiration island)."""
        num_islands = 3
        approaches = [
            _make_approach(
                island=0, task_id="1.1", test_pass_rate=0.9,
                file_patterns=["scripts/evo_db.py"],
                task_type="backend",
            ),
        ]
        db_dir = _create_db_with_approaches(tmp_path, approaches, num_islands=num_islands)

        plan_path = _write_plan(tmp_path, [
            {
                "id": "1.1", "name": "Evo DB", "status": "completed",
                "depends_on": [],
                "file_scope": ["scripts/evo_db.py"],
            },
            {
                "id": "1.2", "name": "Pollinator", "status": "pending",
                "depends_on": [],
                "file_scope": ["scripts/evo_db.py", "scripts/plan_utils.py"],
            },
        ])

        result = pollinate(db_dir, plan_path, "1.2", threshold=0.1)
        assert result["migrated"] >= 1
        # Inspiration island is the last one: num_islands - 1 = 2
        assert result["target_island"] == num_islands - 1

        # Verify the approach is actually on the inspiration island in the DB
        db = EvolutionDB(config={"num_islands": num_islands})
        db.load(db_dir)
        inspiration_approaches = [
            a for a in db.approaches.values() if a.island == num_islands - 1
        ]
        assert len(inspiration_approaches) >= 1


# ---------------------------------------------------------------------------
# T9  test_pollinate_no_completed_tasks
# ---------------------------------------------------------------------------

class TestPollinateNoCompletedTasks:
    def test_pollinate_no_completed_tasks(self, tmp_path):
        """pollinate() returns empty migration when no tasks are completed."""
        db_dir = _create_db_with_approaches(tmp_path, [])

        plan_path = _write_plan(tmp_path, [
            {
                "id": "1.1", "name": "Task A", "status": "pending",
                "depends_on": [],
                "file_scope": ["scripts/evo_db.py"],
            },
        ])

        result = pollinate(db_dir, plan_path, "1.1", threshold=0.3)
        assert result["migrated"] == 0
        assert result["source_tasks"] == []


# ---------------------------------------------------------------------------
# T10  test_pollinate_missing_population
# ---------------------------------------------------------------------------

class TestPollinateMissingPopulation:
    def test_pollinate_missing_population(self, tmp_path):
        """pollinate() handles an empty/missing DB gracefully."""
        db_dir = str(tmp_path / "empty_db")
        os.makedirs(db_dir, exist_ok=True)

        plan_path = _write_plan(tmp_path, [
            {
                "id": "1.1", "name": "Task A", "status": "completed",
                "depends_on": [],
                "file_scope": ["scripts/evo_db.py"],
            },
            {
                "id": "1.2", "name": "Task B", "status": "pending",
                "depends_on": [],
                "file_scope": ["scripts/evo_db.py"],
            },
        ])

        result = pollinate(db_dir, plan_path, "1.2", threshold=0.3)
        assert result["migrated"] == 0
        assert result["source_tasks"] == []
