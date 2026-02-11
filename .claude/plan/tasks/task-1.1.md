# Task 1.1: Population Database with MAP-Elites and Islands

## Goal (from must_haves)
**Truths:**
- Approach dataclass stores id, prompt_addendum, parent_id, generation, metrics, island, feature_coords, task_id, task_type, file_patterns, artifacts, timestamp, and iteration
- EvolutionDB.add() places approaches in a MAP-Elites grid using min-max binning, replacing only if the new approach has a better score
- EvolutionDB.sample() uses three-tier selection: 20% exploration (random), 70% exploitation (archive/best), 10% fitness-weighted
- Inspirations are always sampled from DIFFERENT islands than the parent
- EvolutionDB.migrate() copies best approach from source to target island using ring topology
- save/load persists to JSONL for approaches + JSON for metadata
- CLI supports --add, --sample, --stats, --best, --migrate

**Artifacts:**
- scripts/evo_db.py
- tests/python/test_evo_db.py

## Context
This is the foundational data structure for the evolutionary intelligence system. It replaces the flat learnings.jsonl storage (scripts/learnings.py) with a structured population database inspired by OpenEvolve's MAP-Elites algorithm with island-based populations.

The key insight from OpenEvolve (see /home/user/openevolve/openevolve/database.py) is that MAP-Elites maintains diversity by mapping approaches to a multi-dimensional feature grid where each cell holds only the best approach for that region of feature space. Island-based populations evolve independently with periodic migration, preventing premature convergence.

In this system, the "program" being evolved is NOT code -- it is the **approach/strategy addendum** prepended to task prompts. The executor agent (Claude) naturally "mutates" approaches when given rich evolution context. The population stores these approach addendums alongside their evaluation metrics.

## Backend Deliverables
Create `scripts/evo_db.py`:

### Approach Dataclass
```python
@dataclass
class Approach:
    id: str                          # UUID
    prompt_addendum: str             # The evolved strategy text
    parent_id: Optional[str]         # Parent approach ID (None for seed)
    generation: int                  # Evolution generation number
    metrics: Dict[str, float]        # {test_pass_rate, duration_s, complexity, ...}
    island: int                      # Island index (0 to num_islands-1)
    feature_coords: Tuple[int, ...]  # Binned coordinates in MAP-Elites grid
    task_id: str                     # Task this approach was generated for
    task_type: str                   # Inferred task type (backend, frontend, etc.)
    file_patterns: List[str]         # File scope patterns
    artifacts: Dict[str, str]        # {test_output, error_trace}
    timestamp: float                 # time.time()
    iteration: int                   # VGL iteration where this was produced
```

### EvolutionDB Class
```python
class EvolutionDB:
    def __init__(self, config=None):
        # Defaults: num_islands=3, feature_dimensions=["test_pass_rate", "complexity"],
        # feature_bins=10, exploration_ratio=0.2, exploitation_ratio=0.7

    def add(self, approach: Approach) -> str:
        # 1. Calculate feature coords via min-max binning across feature_dimensions
        # 2. Convert to grid key: tuple of bin indices (0 to feature_bins-1)
        # 3. Check island's feature map for existing approach at same coords
        # 4. Replace only if new approach has higher test_pass_rate (or cell empty)
        # 5. Track in island population set
        # 6. Update best-per-island and global best tracking
        # Returns approach.id

    def sample(self, island_id, num_inspirations=2):
        # Three-tier parent selection based on random roll:
        #   rand < 0.2 (exploration): random approach from island
        #   rand < 0.9 (exploitation): from archive/best approaches on island
        #   else (weighted): fitness-proportional selection from island
        # Inspirations sampled from DIFFERENT islands (not parent's island)
        # Returns (parent_approach, [inspiration_approaches])

    def get_best(self) -> Optional[Approach]:
        # Return highest test_pass_rate approach across all islands

    def migrate(self, source_island: int, target_island: int):
        # Copy best approach from source island to target island
        # Ring topology: island 0 -> 1 -> 2 -> 0
        # Migrated approach gets new ID, keeps parent_id pointing to original

    def save(self, path: str):
        # approaches.jsonl: one JSON object per approach per line
        # metadata.json: feature_maps, island assignments, best tracking, config

    def load(self, path: str):
        # Reconstruct full state from approaches.jsonl + metadata.json

    def stats(self) -> dict:
        # Return population count, per-island counts, best score, generation stats
```

### Storage
- Path: `.planning/evolution/{task_id}/`
- Files: `approaches.jsonl`, `metadata.json`, `approaches.jsonl.lock`
- Thread-safe: use `fcntl.flock` for concurrent access (matching `plan_utils.py` pattern from run_history.py)

### CLI Interface
```bash
python3 evo_db.py --db-path .planning/evolution/1.1/ --add '{"prompt_addendum":"...", "metrics":{...}, ...}'
python3 evo_db.py --db-path .planning/evolution/1.1/ --sample 0        # sample from island 0
python3 evo_db.py --db-path .planning/evolution/1.1/ --stats
python3 evo_db.py --db-path .planning/evolution/1.1/ --best
python3 evo_db.py --db-path .planning/evolution/1.1/ --migrate 0 1     # migrate best from island 0 to 1
```
All CLI output is JSON for programmatic consumption.

### Feature Coordinate Calculation (min-max binning)
For each feature dimension:
1. Track running min/max across all approaches in the population
2. Normalize value to [0, 1] range: `(value - min) / (max - min)`
3. Bin to integer: `min(int(normalized * feature_bins), feature_bins - 1)`
4. First approach (no min/max range): place at bin 0
5. When min == max: place at bin `feature_bins // 2`

## Frontend Deliverables
- CLI output is JSON for programmatic consumption
- `--stats` includes: `{total_approaches, per_island: [{count, best_score, generations}], global_best: {id, score, generation}}`
- `--sample` outputs: `{parent: {...}, inspirations: [{...}, ...]}`
- `--best` outputs the full Approach as JSON

## Tests to Write (TDD-First)

### tests/python/test_evo_db.py
- test_approach_creation -- all fields present in Approach dataclass
- test_add_places_in_grid -- approach added at correct feature coordinates in island's feature map
- test_add_replaces_if_better -- higher test_pass_rate replaces lower in same MAP-Elites cell
- test_add_keeps_if_worse -- lower test_pass_rate does not replace higher in same cell
- test_sample_returns_parent_and_inspirations -- returns tuple of (Approach, list[Approach])
- test_sample_exploration -- with mocked random returning 0.1, selects random approach from island
- test_sample_exploitation -- with mocked random returning 0.5, selects from archive/best
- test_sample_weighted -- with mocked random returning 0.95, uses fitness-weighted selection
- test_sample_inspirations_different_island -- inspiration approaches have different island than parent
- test_get_best -- returns approach with highest test_pass_rate across all islands
- test_migrate_ring_topology -- migrate(0, 1) copies island 0's best to island 1
- test_feature_coords_binning -- min-max scaling produces correct bin indices for known values
- test_save_load_roundtrip -- save then load preserves all approaches, metadata, and island assignments
- test_empty_population_sample -- sample on empty DB returns None gracefully without crash
- test_empty_population_stats -- stats returns zeros/empty for empty population
- test_island_isolation -- approaches added to island 0 do not appear in island 1's population

## Test Dependency Graph

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | tests/python/test_evo_db.py | -- | Create evo_db.py with Approach dataclass + EvolutionDB. Reference /home/user/openevolve/openevolve/database.py for MAP-Elites algorithm (ProgramDatabase.add, sample_from_island, _calculate_feature_coords, save/load). Use dataclasses, json, os, fcntl, uuid, time, random. Use tmp_path for storage directory. No external deps beyond stdlib. |

Dispatch order:
- Wave 1: T1

## Key Links
- OpenEvolve reference: /home/user/openevolve/openevolve/database.py (MAP-Elites, islands, sampling)
- Existing locking pattern: scripts/run_history.py (_history_lock using fcntl.flock)
- Replaces: scripts/learnings.py (flat JSONL storage with no population structure)

## Technical Notes
- Dependencies: stdlib only (dataclasses, json, os, fcntl, uuid, time, random, argparse)
- MAP-Elites grid: dict mapping tuple(feature_coords) -> approach_id, one grid per island
- Feature dimensions default to ["test_pass_rate", "complexity"] -- these are the axes of the MAP-Elites grid
- Island count defaults to 3 -- small enough for CLI task iteration counts (typically 3-10 iterations)
- exploration_ratio=0.2, exploitation_ratio=0.7 leaves 0.1 for fitness-weighted sampling
- Ring topology for migration: island N migrates to island (N+1) % num_islands
- JSONL format for approaches enables append-only writes (same pattern as run_history.py)
- Thread safety via flock prevents corruption when stop-hook and executor access concurrently
- Approach.prompt_addendum is the core evolved artifact -- a markdown string prepended to task prompts
