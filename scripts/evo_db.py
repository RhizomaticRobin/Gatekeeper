#!/usr/bin/env python3
"""Evolution population database with MAP-Elites and island-based populations.

Implements a MAP-Elites algorithm with island-based evolution for the GSD-VGL
system. Replaces flat learnings.jsonl with a structured population database
inspired by OpenEvolve's database.py.

The "program" being evolved is the approach/strategy addendum prepended to
task prompts. The executor agent (Claude) naturally "mutates" approaches when
given rich evolution context.

Classes:
    Approach    — dataclass holding an evolved strategy and its evaluation metrics
    EvolutionDB — MAP-Elites population database with island-based populations

CLI:
    python3 evo_db.py --db-path PATH --add JSON
    python3 evo_db.py --db-path PATH --sample ISLAND_ID
    python3 evo_db.py --db-path PATH --stats
    python3 evo_db.py --db-path PATH --best
    python3 evo_db.py --db-path PATH --migrate SRC DST
"""

import argparse
import copy
import fcntl
import json
import os
import random
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Approach dataclass
# ---------------------------------------------------------------------------

@dataclass
class Approach:
    """A single evolved strategy/approach in the population."""

    id: str                                    # UUID
    prompt_addendum: str                       # The evolved strategy text
    parent_id: Optional[str]                   # Parent approach ID (None for seed)
    generation: int                            # Evolution generation number
    metrics: Dict[str, float]                  # {test_pass_rate, duration_s, complexity, ...}
    island: int                                # Island index (0 to num_islands-1)
    feature_coords: Tuple[int, ...]            # Binned coordinates in MAP-Elites grid
    task_id: str                               # Task this approach was generated for
    task_type: str                             # Inferred task type (backend, frontend, etc.)
    file_patterns: List[str]                   # File scope patterns
    artifacts: Dict[str, str]                  # {test_output, error_trace}
    timestamp: float                           # time.time()
    iteration: int                             # VGL iteration

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict (JSON-safe)."""
        d = asdict(self)
        # Ensure feature_coords is stored as a list for JSON
        d["feature_coords"] = list(self.feature_coords)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Approach":
        """Deserialize from a dict."""
        data = dict(data)  # shallow copy
        # Convert feature_coords back to tuple
        if "feature_coords" in data:
            data["feature_coords"] = tuple(data["feature_coords"])
        return cls(**data)


# ---------------------------------------------------------------------------
# File-lock helper (matches run_history.py pattern)
# ---------------------------------------------------------------------------

@contextmanager
def _db_lock(db_dir: str):
    """Acquire an exclusive flock for thread-safe access."""
    lock_path = os.path.join(db_dir, "approaches.jsonl.lock")
    os.makedirs(db_dir, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------------------------------------------------------------------------
# EvolutionDB
# ---------------------------------------------------------------------------

class EvolutionDB:
    """MAP-Elites population database with island-based evolution.

    Parameters (via config dict):
        num_islands         — number of isolated populations (default 3)
        feature_dimensions  — list of metric keys used as MAP-Elites axes
                              (default ["test_pass_rate", "complexity"])
        feature_bins        — number of bins per feature dimension (default 10)
        exploration_ratio   — probability of random selection (default 0.2)
        exploitation_ratio  — probability of archive/best selection (default 0.7)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.num_islands: int = cfg.get("num_islands", 3)
        self.feature_dimensions: List[str] = cfg.get(
            "feature_dimensions", ["test_pass_rate", "complexity"]
        )
        self.feature_bins: int = cfg.get("feature_bins", 10)
        self.exploration_ratio: float = cfg.get("exploration_ratio", 0.2)
        self.exploitation_ratio: float = cfg.get("exploitation_ratio", 0.7)

        # In-memory storage
        self.approaches: Dict[str, Approach] = {}

        # Per-island MAP-Elites grid: feature_coords_key -> approach_id
        self.island_feature_maps: List[Dict[str, str]] = [
            {} for _ in range(self.num_islands)
        ]

        # Running min/max for each feature dimension (for binning)
        self._feature_min: Dict[str, float] = {}
        self._feature_max: Dict[str, float] = {}

        # Best tracking
        self._best_per_island: List[Optional[str]] = [None] * self.num_islands
        self._global_best_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, approach: Approach) -> str:
        """Add an approach to the database.

        1. Calculate feature coords via min-max binning.
        2. Place in the island's MAP-Elites grid.
        3. Replace only if the new approach has a better test_pass_rate (or cell is empty).
        4. Track best per island and global best.

        Returns the approach id.
        """
        # Update running min/max stats FIRST
        for dim in self.feature_dimensions:
            val = approach.metrics.get(dim, 0.0)
            if dim not in self._feature_min:
                self._feature_min[dim] = val
                self._feature_max[dim] = val
            else:
                self._feature_min[dim] = min(self._feature_min[dim], val)
                self._feature_max[dim] = max(self._feature_max[dim], val)

        # Calculate feature coords
        coords = self._calculate_feature_coords(approach)
        approach = Approach(
            id=approach.id,
            prompt_addendum=approach.prompt_addendum,
            parent_id=approach.parent_id,
            generation=approach.generation,
            metrics=approach.metrics,
            island=approach.island,
            feature_coords=tuple(coords),
            task_id=approach.task_id,
            task_type=approach.task_type,
            file_patterns=approach.file_patterns,
            artifacts=approach.artifacts,
            timestamp=approach.timestamp,
            iteration=approach.iteration,
        )

        # Store the approach
        self.approaches[approach.id] = approach

        # Place in MAP-Elites grid
        island_idx = approach.island % self.num_islands
        fmap = self.island_feature_maps[island_idx]
        fkey = self._coords_to_key(coords)

        if fkey not in fmap:
            # Empty cell -- place directly
            fmap[fkey] = approach.id
        else:
            existing_id = fmap[fkey]
            if existing_id in self.approaches:
                existing = self.approaches[existing_id]
                if self._is_better(approach, existing):
                    fmap[fkey] = approach.id
            else:
                # Stale reference
                fmap[fkey] = approach.id

        # Update best tracking
        self._update_best(approach, island_idx)

        return approach.id

    def sample(
        self,
        island_id: int,
        num_inspirations: int = 2,
    ) -> Optional[Tuple[Approach, List[Approach]]]:
        """Sample a parent approach and cross-island inspirations.

        Three-tier parent selection (from the requested island):
            rand < exploration_ratio (0.2):  random approach from island
            rand < exploration + exploitation (0.9): best/archive from island
            else (0.1):  fitness-weighted selection from island

        Inspirations are always sampled from DIFFERENT islands.

        Returns (parent, [inspirations]) or None if the population is empty.
        """
        island_id = island_id % self.num_islands
        island_approaches = self._get_island_approaches(island_id)

        if not island_approaches:
            return None

        # Three-tier parent selection
        rand_val = random.random()
        if rand_val < self.exploration_ratio:
            # Exploration: random
            parent = random.choice(island_approaches)
        elif rand_val < self.exploration_ratio + self.exploitation_ratio:
            # Exploitation: best from island
            parent = self._get_island_best_approach(island_id)
            if parent is None:
                parent = random.choice(island_approaches)
        else:
            # Fitness-weighted
            parent = self._fitness_weighted_sample(island_approaches)

        # Sample inspirations from DIFFERENT islands
        inspirations = self._sample_cross_island(island_id, num_inspirations)

        return parent, inspirations

    def get_best(self) -> Optional[Approach]:
        """Return the approach with the highest test_pass_rate across all islands."""
        if not self.approaches:
            return None

        if self._global_best_id and self._global_best_id in self.approaches:
            return self.approaches[self._global_best_id]

        # Recalculate
        best = max(
            self.approaches.values(),
            key=lambda a: a.metrics.get("test_pass_rate", 0.0),
        )
        self._global_best_id = best.id
        return best

    def migrate(self, source_island: int, target_island: int) -> Optional[str]:
        """Copy the best approach from source island to target island.

        Ring topology: island N migrates to island (N+1) % num_islands.
        The migrated approach gets a new ID with parent_id pointing to the original.

        Returns the new approach id, or None if source island is empty.
        """
        source_island = source_island % self.num_islands
        target_island = target_island % self.num_islands

        best = self._get_island_best_approach(source_island)
        if best is None:
            return None

        # Create a copy with new id and updated island
        migrated = Approach(
            id=str(uuid.uuid4()),
            prompt_addendum=best.prompt_addendum,
            parent_id=best.id,
            generation=best.generation + 1,
            metrics=dict(best.metrics),
            island=target_island,
            feature_coords=(),  # will be recalculated by add()
            task_id=best.task_id,
            task_type=best.task_type,
            file_patterns=list(best.file_patterns),
            artifacts=dict(best.artifacts),
            timestamp=time.time(),
            iteration=best.iteration,
        )

        self.add(migrated)
        return migrated.id

    def save(self, path: str) -> None:
        """Persist the database to disk.

        Files written:
            path/approaches.jsonl  — one JSON object per line
            path/metadata.json     — feature maps, config, best tracking
        """
        os.makedirs(path, exist_ok=True)

        with _db_lock(path):
            # Write approaches
            jsonl_path = os.path.join(path, "approaches.jsonl")
            with open(jsonl_path, "w") as f:
                for a in self.approaches.values():
                    f.write(json.dumps(a.to_dict()) + "\n")

            # Write metadata
            meta = {
                "num_islands": self.num_islands,
                "feature_dimensions": self.feature_dimensions,
                "feature_bins": self.feature_bins,
                "exploration_ratio": self.exploration_ratio,
                "exploitation_ratio": self.exploitation_ratio,
                "island_feature_maps": self.island_feature_maps,
                "best_per_island": self._best_per_island,
                "global_best_id": self._global_best_id,
                "feature_min": self._feature_min,
                "feature_max": self._feature_max,
            }
            meta_path = os.path.join(path, "metadata.json")
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)

    def load(self, path: str) -> None:
        """Load the database from disk."""
        jsonl_path = os.path.join(path, "approaches.jsonl")
        meta_path = os.path.join(path, "metadata.json")

        if not os.path.exists(jsonl_path):
            return

        # Load approaches
        self.approaches.clear()
        with open(jsonl_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    a = Approach.from_dict(data)
                    self.approaches[a.id] = a

        # Load metadata
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                meta = json.load(f)

            self.num_islands = meta.get("num_islands", self.num_islands)
            self.feature_dimensions = meta.get("feature_dimensions", self.feature_dimensions)
            self.feature_bins = meta.get("feature_bins", self.feature_bins)
            self.exploration_ratio = meta.get("exploration_ratio", self.exploration_ratio)
            self.exploitation_ratio = meta.get("exploitation_ratio", self.exploitation_ratio)
            self.island_feature_maps = meta.get(
                "island_feature_maps",
                [{} for _ in range(self.num_islands)],
            )
            self._best_per_island = meta.get(
                "best_per_island",
                [None] * self.num_islands,
            )
            self._global_best_id = meta.get("global_best_id")
            self._feature_min = meta.get("feature_min", {})
            self._feature_max = meta.get("feature_max", {})

            # Ensure correct number of islands
            while len(self.island_feature_maps) < self.num_islands:
                self.island_feature_maps.append({})
            while len(self._best_per_island) < self.num_islands:
                self._best_per_island.append(None)

    def stats(self) -> Dict[str, Any]:
        """Return population statistics."""
        per_island = []
        for i in range(self.num_islands):
            island_apps = self._get_island_approaches(i)
            best = self._get_island_best_approach(i)
            per_island.append({
                "island": i,
                "count": len(island_apps),
                "best_score": best.metrics.get("test_pass_rate", 0.0) if best else None,
                "feature_map_cells": len(self.island_feature_maps[i]),
            })

        global_best = self.get_best()
        total_cells = sum(len(fm) for fm in self.island_feature_maps)
        max_cells = self.num_islands * (self.feature_bins ** len(self.feature_dimensions))

        return {
            "population_size": len(self.approaches),
            "num_islands": self.num_islands,
            "best_score": global_best.metrics.get("test_pass_rate", 0.0) if global_best else None,
            "per_island": per_island,
            "feature_map_coverage": total_cells / max_cells if max_cells > 0 else 0.0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_feature_coords(self, approach: Approach) -> List[int]:
        """Calculate MAP-Elites feature coordinates via min-max binning."""
        coords = []
        num_approaches = len(self.approaches)

        for dim in self.feature_dimensions:
            val = approach.metrics.get(dim, 0.0)
            lo = self._feature_min.get(dim, val)
            hi = self._feature_max.get(dim, val)

            if num_approaches == 0:
                # Very first approach: bin 0
                coords.append(0)
            elif lo == hi:
                # All values identical: place at middle bin
                coords.append(self.feature_bins // 2)
            else:
                normalized = (val - lo) / (hi - lo)
                bin_idx = min(int(normalized * self.feature_bins), self.feature_bins - 1)
                bin_idx = max(0, bin_idx)
                coords.append(bin_idx)

        return coords

    @staticmethod
    def _coords_to_key(coords: List[int]) -> str:
        """Convert coordinate list to a hashable dict key string."""
        return ",".join(str(c) for c in coords)

    @staticmethod
    def _is_better(new: Approach, existing: Approach) -> bool:
        """Return True if new approach is better than existing (higher test_pass_rate)."""
        return new.metrics.get("test_pass_rate", 0.0) > existing.metrics.get("test_pass_rate", 0.0)

    def _update_best(self, approach: Approach, island_idx: int) -> None:
        """Update best tracking for an approach."""
        tpr = approach.metrics.get("test_pass_rate", 0.0)

        # Per-island best
        current_best_id = self._best_per_island[island_idx]
        if current_best_id is None or current_best_id not in self.approaches:
            self._best_per_island[island_idx] = approach.id
        else:
            current_best = self.approaches[current_best_id]
            if tpr > current_best.metrics.get("test_pass_rate", 0.0):
                self._best_per_island[island_idx] = approach.id

        # Global best
        if self._global_best_id is None or self._global_best_id not in self.approaches:
            self._global_best_id = approach.id
        else:
            global_best = self.approaches[self._global_best_id]
            if tpr > global_best.metrics.get("test_pass_rate", 0.0):
                self._global_best_id = approach.id

    def _get_island_approaches(self, island_id: int) -> List[Approach]:
        """Return all approaches belonging to an island."""
        return [
            a for a in self.approaches.values()
            if a.island == island_id
        ]

    def _get_island_best_approach(self, island_id: int) -> Optional[Approach]:
        """Return the best approach on an island."""
        best_id = self._best_per_island[island_id]
        if best_id and best_id in self.approaches:
            return self.approaches[best_id]

        # Recalculate
        island_apps = self._get_island_approaches(island_id)
        if not island_apps:
            return None
        best = max(island_apps, key=lambda a: a.metrics.get("test_pass_rate", 0.0))
        self._best_per_island[island_id] = best.id
        return best

    def _fitness_weighted_sample(self, approaches: List[Approach]) -> Approach:
        """Sample an approach with probability proportional to test_pass_rate."""
        if not approaches:
            raise ValueError("Cannot sample from empty list")

        weights = [max(a.metrics.get("test_pass_rate", 0.0), 1e-6) for a in approaches]
        total = sum(weights)
        if total <= 0:
            return random.choice(approaches)

        r = random.uniform(0, total)
        cumulative = 0.0
        for a, w in zip(approaches, weights):
            cumulative += w
            if cumulative >= r:
                return a
        return approaches[-1]  # fallback

    def _sample_cross_island(self, exclude_island: int, n: int) -> List[Approach]:
        """Sample n inspiration approaches from islands other than exclude_island."""
        other_approaches = [
            a for a in self.approaches.values()
            if a.island != exclude_island
        ]
        if not other_approaches:
            return []
        if len(other_approaches) <= n:
            return list(other_approaches)
        return random.sample(other_approaches, n)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="GSD-VGL Evolution Population Database")
    parser.add_argument("--db-path", required=True, help="Path to database directory")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", metavar="JSON", help="Add an approach (JSON string)")
    group.add_argument("--sample", metavar="ISLAND_ID", type=int, help="Sample from island")
    group.add_argument("--stats", action="store_true", help="Show population statistics")
    group.add_argument("--best", action="store_true", help="Show the best approach")
    group.add_argument("--migrate", nargs=2, metavar=("SRC", "DST"), type=int,
                       help="Migrate best from SRC island to DST island")

    args = parser.parse_args()
    db_path = args.db_path

    db = EvolutionDB()
    if os.path.exists(os.path.join(db_path, "approaches.jsonl")):
        db.load(db_path)

    if args.add:
        data = json.loads(args.add)
        # Fill in defaults for CLI usage
        data.setdefault("id", str(uuid.uuid4()))
        data.setdefault("parent_id", None)
        data.setdefault("generation", 0)
        data.setdefault("metrics", {})
        data.setdefault("island", 0)
        data.setdefault("feature_coords", ())
        data.setdefault("task_id", "")
        data.setdefault("task_type", "")
        data.setdefault("file_patterns", [])
        data.setdefault("artifacts", {})
        data.setdefault("timestamp", time.time())
        data.setdefault("iteration", 0)
        data.setdefault("prompt_addendum", "")
        approach = Approach.from_dict(data)
        aid = db.add(approach)
        db.save(db_path)
        print(json.dumps({"status": "added", "id": aid}))

    elif args.sample is not None:
        result = db.sample(island_id=args.sample)
        if result is None:
            print(json.dumps({"parent": None, "inspirations": []}))
        else:
            parent, inspirations = result
            print(json.dumps({
                "parent": parent.to_dict(),
                "inspirations": [i.to_dict() for i in inspirations],
            }))

    elif args.stats:
        print(json.dumps(db.stats(), indent=2))

    elif args.best:
        best = db.get_best()
        if best is None:
            print(json.dumps(None))
        else:
            print(json.dumps(best.to_dict(), indent=2))

    elif args.migrate:
        src, dst = args.migrate
        new_id = db.migrate(src, dst)
        db.save(db_path)
        print(json.dumps({"status": "migrated", "new_id": new_id}))


if __name__ == "__main__":
    main()
