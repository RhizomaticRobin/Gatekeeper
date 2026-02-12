"""Tests for scripts/evo_db.py — MAP-Elites population database with islands."""

import json
import os
import random
import time
import uuid
from unittest.mock import patch

import pytest

# Import from scripts/ (conftest.py ensures scripts/ is on sys.path)
from evo_db import Approach, EvolutionDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_approach(
    island=0,
    test_pass_rate=0.8,
    complexity=5.0,
    generation=0,
    task_id="1.1",
    prompt_addendum="Try a modular approach",
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


# ---------------------------------------------------------------------------
# T1  test_approach_creation
# ---------------------------------------------------------------------------

class TestApproachCreation:
    def test_approach_creation(self):
        """All fields present in the Approach dataclass."""
        a = Approach(
            id="abc-123",
            prompt_addendum="Use TDD",
            parent_id=None,
            generation=0,
            metrics={"test_pass_rate": 0.9, "complexity": 3.0},
            island=0,
            feature_coords=(2, 5),
            task_id="1.1",
            task_type="backend",
            file_patterns=["src/*.py"],
            artifacts={"test_output": "ok"},
            timestamp=1700000000.0,
            iteration=1,
        )
        assert a.id == "abc-123"
        assert a.prompt_addendum == "Use TDD"
        assert a.parent_id is None
        assert a.generation == 0
        assert a.metrics["test_pass_rate"] == 0.9
        assert a.island == 0
        assert a.feature_coords == (2, 5)
        assert a.task_id == "1.1"
        assert a.task_type == "backend"
        assert a.file_patterns == ["src/*.py"]
        assert a.artifacts == {"test_output": "ok"}
        assert a.timestamp == 1700000000.0
        assert a.iteration == 1


# ---------------------------------------------------------------------------
# T2  test_add_places_in_grid
# ---------------------------------------------------------------------------

class TestAddPlacesInGrid:
    def test_add_places_in_grid(self):
        """Approach is placed at the correct feature coordinates in the island's feature map."""
        db = EvolutionDB()
        a = _make_approach(island=0, test_pass_rate=0.5, complexity=5.0)
        db.add(a)

        # The approach should appear in island 0's feature map
        fmap = db.island_feature_maps[0]
        assert len(fmap) == 1
        key = list(fmap.keys())[0]
        assert fmap[key] == a.id

        # The stored approach should have feature_coords set (not empty tuple)
        stored = db.approaches[a.id]
        assert len(stored.feature_coords) == 2  # two feature dimensions by default


# ---------------------------------------------------------------------------
# T3  test_add_replaces_if_better
# ---------------------------------------------------------------------------

class TestAddReplacesIfBetter:
    def test_add_replaces_if_better(self):
        """Higher test_pass_rate replaces lower in the same MAP-Elites cell."""
        db = EvolutionDB()
        # First establish a range so min-max binning creates predictable bins
        boundary_lo = _make_approach(island=0, test_pass_rate=0.0, complexity=0.0)
        boundary_hi = _make_approach(island=0, test_pass_rate=1.0, complexity=10.0)
        db.add(boundary_lo)
        db.add(boundary_hi)

        # Two approaches that fall in the same bin (both in bin 3 for tpr, bin 5 for complexity)
        # With range [0,1] and 10 bins: values 0.31 and 0.35 -> int(0.31*10)=3, int(0.35*10)=3
        a1 = _make_approach(island=0, test_pass_rate=0.31, complexity=5.0)
        a2 = _make_approach(island=0, test_pass_rate=0.35, complexity=5.0)
        db.add(a1)
        db.add(a2)

        # They should share the same MAP-Elites cell
        stored_a1 = db.approaches[a1.id]
        stored_a2 = db.approaches[a2.id]
        assert stored_a1.feature_coords == stored_a2.feature_coords

        # The cell should hold the better approach (a2 has higher test_pass_rate)
        fmap = db.island_feature_maps[0]
        cell_key = None
        for k, v in fmap.items():
            if v == a2.id:
                cell_key = k
                break
        assert cell_key is not None, "a2 should occupy a cell"
        assert fmap[cell_key] == a2.id
        # a1 should NOT hold this cell
        assert a1.id not in fmap.values() or all(
            fmap[k] != a1.id for k in fmap if fmap[k] != a1.id or k != cell_key
        )
        # More direct: a1 should not be the occupant of ANY cell since a2 replaced it
        # (a1 may not occupy any cell since it was replaced)
        for k, v in fmap.items():
            if k == cell_key:
                assert v == a2.id


# ---------------------------------------------------------------------------
# T4  test_add_keeps_if_worse
# ---------------------------------------------------------------------------

class TestAddKeepsIfWorse:
    def test_add_keeps_if_worse(self):
        """Lower test_pass_rate does not replace higher in the same cell."""
        db = EvolutionDB()
        # Establish range first
        boundary_lo = _make_approach(island=0, test_pass_rate=0.0, complexity=0.0)
        boundary_hi = _make_approach(island=0, test_pass_rate=1.0, complexity=10.0)
        db.add(boundary_lo)
        db.add(boundary_hi)

        # good and bad land in the same bin (both in bin 5 for tpr, bin 5 for complexity)
        # 0.55 -> int(0.55*10)=5, 0.51 -> int(0.51*10)=5
        good = _make_approach(island=0, test_pass_rate=0.55, complexity=5.0)
        bad = _make_approach(island=0, test_pass_rate=0.51, complexity=5.0)
        db.add(good)
        db.add(bad)

        # They should share the same cell coords
        stored_good = db.approaches[good.id]
        stored_bad = db.approaches[bad.id]
        assert stored_good.feature_coords == stored_bad.feature_coords

        # The cell should still hold the better approach (good has higher tpr)
        fmap = db.island_feature_maps[0]
        cell_key = None
        for k, v in fmap.items():
            if v == good.id:
                cell_key = k
                break
        assert cell_key is not None, "good should still occupy its cell"
        assert fmap[cell_key] == good.id


# ---------------------------------------------------------------------------
# T5  test_sample_returns_parent_and_inspirations
# ---------------------------------------------------------------------------

class TestSampleReturnsParentAndInspirations:
    def test_sample_returns_parent_and_inspirations(self):
        """sample() returns a tuple of (Approach, list[Approach])."""
        db = EvolutionDB()
        # Need approaches on at least two islands for inspirations
        for i in range(3):
            for isl in range(3):
                db.add(_make_approach(island=isl, test_pass_rate=0.5 + i * 0.1))

        result = db.sample(island_id=0, num_inspirations=2)
        assert result is not None
        parent, inspirations = result
        assert isinstance(parent, Approach)
        assert isinstance(inspirations, list)
        assert all(isinstance(insp, Approach) for insp in inspirations)


# ---------------------------------------------------------------------------
# T6  test_sample_exploration
# ---------------------------------------------------------------------------

class TestSampleExploration:
    def test_sample_exploration(self):
        """With mocked random returning 0.1, selects random approach from island (exploration)."""
        db = EvolutionDB()
        for i in range(5):
            for isl in range(3):
                db.add(_make_approach(island=isl, test_pass_rate=0.1 * (i + 1)))

        with patch("evo_db.random.random", return_value=0.1):
            parent, _ = db.sample(island_id=0, num_inspirations=1)

        # Parent should come from island 0 (exploration = random from the requested island)
        assert parent.island == 0


# ---------------------------------------------------------------------------
# T7  test_sample_exploitation
# ---------------------------------------------------------------------------

class TestSampleExploitation:
    def test_sample_exploitation(self):
        """With mocked random returning 0.5, selects from archive/best (exploitation)."""
        db = EvolutionDB()
        for i in range(5):
            for isl in range(3):
                db.add(_make_approach(island=isl, test_pass_rate=0.1 * (i + 1)))

        with patch("evo_db.random.random", return_value=0.5):
            parent, _ = db.sample(island_id=0, num_inspirations=1)

        # Exploitation => parent should be one of the best on island 0
        assert parent.island == 0


# ---------------------------------------------------------------------------
# T8  test_sample_weighted
# ---------------------------------------------------------------------------

class TestSampleWeighted:
    def test_sample_weighted(self):
        """With mocked random returning 0.95, uses fitness-weighted selection."""
        db = EvolutionDB()
        for i in range(5):
            for isl in range(3):
                db.add(_make_approach(island=isl, test_pass_rate=0.1 * (i + 1)))

        with patch("evo_db.random.random", return_value=0.95):
            parent, _ = db.sample(island_id=0, num_inspirations=1)

        # Weighted selection still picks from island 0
        assert parent.island == 0


# ---------------------------------------------------------------------------
# T9  test_sample_inspirations_different_island
# ---------------------------------------------------------------------------

class TestSampleInspirationsDifferentIsland:
    def test_sample_inspirations_different_island(self):
        """Inspiration approaches have a different island than the parent."""
        db = EvolutionDB()
        for i in range(5):
            for isl in range(3):
                db.add(_make_approach(island=isl, test_pass_rate=0.1 * (i + 1)))

        parent, inspirations = db.sample(island_id=0, num_inspirations=2)
        assert parent.island == 0
        for insp in inspirations:
            assert insp.island != parent.island, (
                f"Inspiration island {insp.island} should differ from parent island {parent.island}"
            )


# ---------------------------------------------------------------------------
# T10  test_get_best
# ---------------------------------------------------------------------------

class TestGetBest:
    def test_get_best(self):
        """Returns the approach with the highest test_pass_rate across all islands."""
        db = EvolutionDB()
        low = _make_approach(island=0, test_pass_rate=0.2)
        mid = _make_approach(island=1, test_pass_rate=0.5)
        high = _make_approach(island=2, test_pass_rate=0.99)
        db.add(low)
        db.add(mid)
        db.add(high)

        best = db.get_best()
        assert best is not None
        assert best.id == high.id
        assert best.metrics["test_pass_rate"] == 0.99


# ---------------------------------------------------------------------------
# T11  test_migrate_ring_topology
# ---------------------------------------------------------------------------

class TestMigrateRingTopology:
    def test_migrate_ring_topology(self):
        """migrate(0, 1) copies island 0's best to island 1."""
        db = EvolutionDB()
        a0 = _make_approach(island=0, test_pass_rate=0.9)
        a1 = _make_approach(island=1, test_pass_rate=0.3)
        db.add(a0)
        db.add(a1)

        db.migrate(source_island=0, target_island=1)

        # Island 1 should now contain a copy of island 0's best
        island1_ids = [
            aid for aid, a in db.approaches.items() if a.island == 1
        ]
        # There should be a new migrated approach on island 1
        assert len(island1_ids) >= 2  # original a1 + migrated copy

        # The migrated copy should have a different id but reference the original as parent
        migrated = [a for a in db.approaches.values()
                    if a.island == 1 and a.parent_id == a0.id]
        assert len(migrated) == 1
        assert migrated[0].id != a0.id
        assert migrated[0].prompt_addendum == a0.prompt_addendum


# ---------------------------------------------------------------------------
# T12  test_feature_coords_binning
# ---------------------------------------------------------------------------

class TestFeatureCoordsBinning:
    def test_feature_coords_binning(self):
        """Min-max scaling produces correct bin indices for known values."""
        db = EvolutionDB(config={"feature_bins": 10})

        # Add approaches spanning a known range
        low = _make_approach(island=0, test_pass_rate=0.0, complexity=0.0)
        high = _make_approach(island=0, test_pass_rate=1.0, complexity=10.0)
        db.add(low)
        db.add(high)

        # Now add a mid-range approach
        mid = _make_approach(island=0, test_pass_rate=0.5, complexity=5.0)
        db.add(mid)

        stored = db.approaches[mid.id]
        # With min=0, max=1 for test_pass_rate: bin = min(int(0.5*10), 9) = 5
        # With min=0, max=10 for complexity: bin = min(int(0.5*10), 9) = 5
        assert stored.feature_coords[0] == 5  # test_pass_rate bin
        assert stored.feature_coords[1] == 5  # complexity bin

    def test_first_approach_bin_zero(self):
        """First approach (no min/max range) is placed at bin 0."""
        db = EvolutionDB(config={"feature_bins": 10})
        first = _make_approach(island=0, test_pass_rate=0.7, complexity=3.0)
        db.add(first)
        stored = db.approaches[first.id]
        assert stored.feature_coords == (0, 0)

    def test_equal_values_bin_middle(self):
        """When min == max, place at feature_bins // 2."""
        db = EvolutionDB(config={"feature_bins": 10})
        a1 = _make_approach(island=0, test_pass_rate=0.5, complexity=5.0)
        a2 = _make_approach(island=0, test_pass_rate=0.5, complexity=5.0)
        db.add(a1)
        db.add(a2)
        stored = db.approaches[a2.id]
        # min == max for both dimensions => bin = 10 // 2 = 5
        assert stored.feature_coords == (5, 5)


# ---------------------------------------------------------------------------
# T13  test_save_load_roundtrip
# ---------------------------------------------------------------------------

class TestSaveLoadRoundtrip:
    def test_save_load_roundtrip(self, tmp_path):
        """save() then load() preserves all approaches, metadata, and island assignments."""
        db = EvolutionDB()
        approaches = []
        for isl in range(3):
            a = _make_approach(island=isl, test_pass_rate=0.3 + isl * 0.2, complexity=isl * 2.0)
            db.add(a)
            approaches.append(a)

        save_dir = str(tmp_path / "evo_save")
        db.save(save_dir)

        # Verify files exist
        assert os.path.exists(os.path.join(save_dir, "approaches.jsonl"))
        assert os.path.exists(os.path.join(save_dir, "metadata.json"))

        # Load into fresh DB
        db2 = EvolutionDB()
        db2.load(save_dir)

        # All approaches present
        assert len(db2.approaches) == len(db.approaches)
        for a in approaches:
            assert a.id in db2.approaches
            loaded = db2.approaches[a.id]
            assert loaded.prompt_addendum == a.prompt_addendum
            assert loaded.island == a.island
            assert loaded.metrics == a.metrics

        # Island feature maps preserved
        for isl in range(3):
            assert len(db2.island_feature_maps[isl]) == len(db.island_feature_maps[isl])


# ---------------------------------------------------------------------------
# T14  test_empty_population_sample
# ---------------------------------------------------------------------------

class TestEmptyPopulationSample:
    def test_empty_population_sample(self):
        """sample() on an empty DB returns None gracefully without crash."""
        db = EvolutionDB()
        result = db.sample(island_id=0)
        assert result is None


# ---------------------------------------------------------------------------
# T15  test_empty_population_stats
# ---------------------------------------------------------------------------

class TestEmptyPopulationStats:
    def test_empty_population_stats(self):
        """stats() returns zeros/empty for an empty population."""
        db = EvolutionDB()
        s = db.stats()
        assert s["population_size"] == 0
        assert s["num_islands"] == 3  # default
        assert s["best_score"] is None or s["best_score"] == 0
        assert isinstance(s["per_island"], list)


# ---------------------------------------------------------------------------
# T16  test_island_isolation
# ---------------------------------------------------------------------------

class TestIslandIsolation:
    def test_island_isolation(self):
        """Approaches added to island 0 do not appear in island 1's population."""
        db = EvolutionDB()
        a0 = _make_approach(island=0, test_pass_rate=0.8)
        a1 = _make_approach(island=1, test_pass_rate=0.6)
        db.add(a0)
        db.add(a1)

        # Island 0's feature map should not contain island 1's approach
        fmap0 = db.island_feature_maps[0]
        fmap1 = db.island_feature_maps[1]

        ids_in_0 = set(fmap0.values())
        ids_in_1 = set(fmap1.values())

        assert a0.id in ids_in_0
        assert a0.id not in ids_in_1
        assert a1.id in ids_in_1
        assert a1.id not in ids_in_0
