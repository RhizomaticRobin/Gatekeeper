"""Tests for executor parallel island support patterns.

Tests verify the evo_db.py CLI patterns that executor.md (Step 2.5) describes:
- Population stats query
- Multi-island sampling
- Approach addendum format for prompt injection
- Storing candidate results back into population
- Best candidate selection by test_pass_rate
- Empty population skip logic

These are integration tests exercising the CLI the executor agent calls.
"""

import json
import os
import subprocess
import sys
import time
import uuid

import pytest

# Import from scripts/ (conftest.py ensures scripts/ is on sys.path)
from evo_db import Approach, EvolutionDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
EVO_DB_SCRIPT = os.path.join(os.path.abspath(SCRIPTS_DIR), "evo_db.py")


def _make_approach(
    island=0,
    test_pass_rate=0.8,
    complexity=5.0,
    generation=0,
    task_id="2.2",
    prompt_addendum="Try a modular approach with parallel island exploration",
    parent_id=None,
    iteration=0,
    **extra_metrics,
):
    """Create an Approach with sensible defaults for testing."""
    metrics = {"test_pass_rate": test_pass_rate, "complexity": complexity}
    metrics.update(extra_metrics)
    return Approach(
        id=str(uuid.uuid4()),
        prompt_addendum=prompt_addendum,
        parent_id=parent_id,
        generation=generation,
        metrics=metrics,
        island=island,
        feature_coords=(),  # will be calculated by add()
        task_id=task_id,
        task_type="backend",
        file_patterns=["scripts/*.py"],
        artifacts={},
        timestamp=time.time(),
        iteration=iteration,
    )


def _create_fixture_population(db_path, approaches_per_island=2):
    """Create a fixture population with approaches spread across 3 islands.

    Returns the EvolutionDB instance and the list of approaches added.
    """
    db = EvolutionDB()
    approaches = []
    for island in range(3):
        for i in range(approaches_per_island):
            tpr = 0.3 + island * 0.2 + i * 0.05
            a = _make_approach(
                island=island,
                test_pass_rate=tpr,
                complexity=float(island + i),
                prompt_addendum=f"Island {island} approach {i}: use strategy variant {island}-{i}",
                generation=i,
                iteration=i,
            )
            db.add(a)
            approaches.append(a)
    db.save(db_path)
    return db, approaches


def _run_evo_db_cli(*args):
    """Run evo_db.py as a subprocess and return parsed JSON output."""
    cmd = [sys.executable, EVO_DB_SCRIPT] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, (
        f"evo_db.py failed with exit code {result.returncode}:\n"
        f"  stdout: {result.stdout}\n"
        f"  stderr: {result.stderr}"
    )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# test_stats_returns_population_info
# ---------------------------------------------------------------------------

class TestStatsReturnsPopulationInfo:
    """Create fixture population with 5+ approaches, run evo_db.py --stats,
    verify JSON output has total_approaches (population_size) and per_island fields."""

    def test_stats_returns_population_info(self, tmp_path):
        db_path = str(tmp_path / "evo_pop")
        # Create 2 approaches per island = 6 total across 3 islands
        _create_fixture_population(db_path, approaches_per_island=2)

        output = _run_evo_db_cli("--db-path", db_path, "--stats")

        # Must have population_size (the "total_approaches" concept)
        assert "population_size" in output
        assert output["population_size"] == 6

        # Must have per_island breakdown
        assert "per_island" in output
        per_island = output["per_island"]
        assert isinstance(per_island, list)
        assert len(per_island) == 3  # 3 islands

        # Each island entry has count and best_score
        for island_info in per_island:
            assert "island" in island_info
            assert "count" in island_info
            assert island_info["count"] == 2  # 2 approaches per island
            assert "best_score" in island_info
            assert island_info["best_score"] is not None

        # num_islands field
        assert "num_islands" in output
        assert output["num_islands"] == 3


# ---------------------------------------------------------------------------
# test_sample_from_multiple_islands
# ---------------------------------------------------------------------------

class TestSampleFromMultipleIslands:
    """Create fixture population across 3 islands, run evo_db.py --sample 0,
    --sample 1, --sample 2, verify each returns a parent approach."""

    def test_sample_from_multiple_islands(self, tmp_path):
        db_path = str(tmp_path / "evo_pop")
        _create_fixture_population(db_path, approaches_per_island=2)

        parents = []
        for island_id in range(3):
            output = _run_evo_db_cli("--db-path", db_path, "--sample", str(island_id))

            # Must have a parent (not null)
            assert output["parent"] is not None, (
                f"--sample {island_id} returned null parent"
            )

            parent = output["parent"]
            # Parent must have required fields
            assert "id" in parent
            assert "prompt_addendum" in parent
            assert "island" in parent
            assert "metrics" in parent

            # Parent island should match the requested island
            assert parent["island"] == island_id, (
                f"Expected parent from island {island_id}, got island {parent['island']}"
            )

            parents.append(parent)

            # Must have inspirations list (cross-island)
            assert "inspirations" in output
            assert isinstance(output["inspirations"], list)

        # All 3 parents should be different approaches (from different islands)
        parent_ids = [p["id"] for p in parents]
        assert len(set(parent_ids)) == 3, (
            f"Expected 3 unique parents, got IDs: {parent_ids}"
        )


# ---------------------------------------------------------------------------
# test_approach_addendum_format
# ---------------------------------------------------------------------------

class TestApproachAddendumFormat:
    """Verify prompt_addendum field in sampled approach is a non-empty string
    suitable for injection into a task prompt."""

    def test_approach_addendum_format(self, tmp_path):
        db_path = str(tmp_path / "evo_pop")
        _create_fixture_population(db_path, approaches_per_island=2)

        output = _run_evo_db_cli("--db-path", db_path, "--sample", "0")
        parent = output["parent"]

        addendum = parent["prompt_addendum"]

        # Must be a non-empty string
        assert isinstance(addendum, str)
        assert len(addendum.strip()) > 0, "prompt_addendum must be non-empty"

        # Must be suitable for prompt injection (contains meaningful text)
        # Our fixture creates addendums like "Island 0 approach 1: use strategy variant 0-1"
        assert len(addendum) >= 10, (
            f"prompt_addendum too short for meaningful injection: '{addendum}'"
        )

        # Should not contain problematic characters that break prompt templates
        # (JSON control characters, null bytes)
        assert "\x00" not in addendum
        assert addendum == addendum.strip() or addendum.strip() != ""


# ---------------------------------------------------------------------------
# test_store_candidate_results
# ---------------------------------------------------------------------------

class TestStoreCandidateResults:
    """Create fixture, run evo_db.py --add with metrics JSON,
    verify approach count increases."""

    def test_store_candidate_results(self, tmp_path):
        db_path = str(tmp_path / "evo_pop")
        _create_fixture_population(db_path, approaches_per_island=2)

        # Check initial stats
        stats_before = _run_evo_db_cli("--db-path", db_path, "--stats")
        count_before = stats_before["population_size"]
        assert count_before == 6

        # Add a new candidate result (as the executor would after evaluation)
        new_approach_json = json.dumps({
            "prompt_addendum": "Use event-driven architecture with message queues",
            "island": 1,
            "metrics": {
                "test_pass_rate": 0.85,
                "complexity": 7.0,
            },
            "task_id": "2.2",
            "task_type": "backend",
            "generation": 1,
            "iteration": 3,
        })

        add_result = _run_evo_db_cli("--db-path", db_path, "--add", new_approach_json)
        assert add_result["status"] == "added"
        assert "id" in add_result

        # Check stats again -- count should have increased
        stats_after = _run_evo_db_cli("--db-path", db_path, "--stats")
        count_after = stats_after["population_size"]
        assert count_after == count_before + 1, (
            f"Expected population to grow from {count_before} to {count_before + 1}, "
            f"got {count_after}"
        )


# ---------------------------------------------------------------------------
# test_best_candidate_selection
# ---------------------------------------------------------------------------

class TestBestCandidateSelection:
    """Create fixture with approaches of varying test_pass_rate,
    run evo_db.py --best, verify returned approach has the highest score."""

    def test_best_candidate_selection(self, tmp_path):
        db_path = str(tmp_path / "evo_pop")

        # Create population with known varying scores
        db = EvolutionDB()
        scores = [0.1, 0.4, 0.6, 0.95, 0.3]  # 0.95 is the best
        best_addendum = "The winning strategy with highest score"
        for i, score in enumerate(scores):
            addendum = best_addendum if score == 0.95 else f"Strategy {i}"
            a = _make_approach(
                island=i % 3,
                test_pass_rate=score,
                complexity=float(i),
                prompt_addendum=addendum,
            )
            db.add(a)
        db.save(db_path)

        # Run --best CLI
        output = _run_evo_db_cli("--db-path", db_path, "--best")

        # Should return the approach with highest test_pass_rate (0.95)
        assert output is not None
        assert output["metrics"]["test_pass_rate"] == 0.95
        assert output["prompt_addendum"] == best_addendum


# ---------------------------------------------------------------------------
# test_empty_population_skips_evolution
# ---------------------------------------------------------------------------

class TestEmptyPopulationSkipsEvolution:
    """Run evo_db.py --stats on empty directory, verify population_size is 0
    (triggers skip logic in executor Step 2.5)."""

    def test_empty_population_skips_evolution(self, tmp_path):
        db_path = str(tmp_path / "empty_evo")
        os.makedirs(db_path, exist_ok=True)

        output = _run_evo_db_cli("--db-path", db_path, "--stats")

        # population_size must be 0 so executor skips evolution
        assert output["population_size"] == 0

        # per_island should show all zeros
        for island_info in output["per_island"]:
            assert island_info["count"] == 0

        # best_score should be None (no approaches)
        assert output["best_score"] is None
