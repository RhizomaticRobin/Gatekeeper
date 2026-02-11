# Task 2.3: Cross-Task Approach Pollination

## Goal (from must_haves)
**Truths:**
- pollinate() loads plan.yaml to find completed tasks and computes similarity to the target task
- Similarity scoring: +3 per exact file path match, +1 per shared directory prefix, +2 for same inferred task type
- Only approaches with test_pass_rate >= 0.5 from completed tasks are migrated
- Migrated approaches are placed on the designated "inspiration island" (last island index)
- Tasks below the similarity threshold (default 0.3) are skipped
- CLI supports --pollinate with target db path, plan path, task id, and optional threshold

**Artifacts:**
- scripts/evo_pollinator.py
- tests/python/test_evo_pollinator.py

## Context
This is the cross-task knowledge transfer component of the evolutionary intelligence system. When a new task starts (first iteration), the pollinator seeds its population with successful approaches from completed similar tasks.

The similarity scoring is adapted from the existing learnings.py _compute_relevance_score() function (see scripts/learnings.py lines 226-262), which uses the same +3/+1/+2 pattern for file path overlap, directory overlap, and task type match. The pollinator extends this to operate on evolution populations rather than flat learning entries.

The pollinator is called by the stop-hook (task 2.1) on the first iteration of a new task. It scans all completed tasks, finds those with similar file scopes, and imports their best approaches onto a designated "inspiration island" in the new task's population. This gives the evolution engine a head start by seeding with proven strategies from related work.

## Backend Deliverables
Create `scripts/evo_pollinator.py`:

### Core Functions
```python
def pollinate(target_db_path: str, plan_path: str, task_id: str, threshold: float = 0.3):
    """Seed target population from completed similar tasks.

    1. Load plan.yaml to find completed tasks (status == "completed")
    2. For each completed task, compute similarity to target task:
       - Extract file_scope from both tasks in plan.yaml
       - Score with _compute_similarity()
       - Normalize to 0.0-1.0 range
    3. For tasks above threshold:
       - Load their population from .planning/evolution/{completed_task_id}/
       - Select top approaches where test_pass_rate >= 0.5
       - Import into target population on the inspiration island
         (island index = num_islands - 1, i.e., island 2 with default 3 islands)
    4. Return count of migrated approaches
    """

def _compute_similarity(task_a_scope: dict, task_b_scope: dict) -> float:
    """Compute file-scope-based similarity between two tasks.

    Scoring (same as learnings.py _compute_relevance_score):
      - Exact file path match in 'owns' lists: +3 per match
      - Shared directory prefix (same parent dir): +1 per match
      - Same inferred task type: +2

    Normalization:
      max_possible = 3 * max(len(a_owns), len(b_owns)) + 2
      return min(1.0, raw_score / max_possible)
    """

def _infer_task_type(file_scope: dict) -> str:
    """Infer task type from file_scope patterns.

    Looks at file extensions in 'owns' list:
      - .py, .sh -> 'backend'
      - .tsx, .jsx, .css -> 'frontend'
      - .test., .spec. -> 'test'
      - .yaml, .json, .md -> 'configuration'
      - fallback -> 'general'

    Similar to learnings.py _infer_task_type but operates on
    file_scope dict rather than free text.
    """
```

### CLI Interface
```bash
python3 evo_pollinator.py --pollinate .planning/evolution/2.1/ .claude/plan/plan.yaml 2.1
python3 evo_pollinator.py --pollinate .planning/evolution/2.1/ .claude/plan/plan.yaml 2.1 --threshold 0.5
```
Output is JSON: `{"migrated": 3, "source_tasks": ["1.1", "1.3"], "target_island": 2}`

### Plan YAML Integration
The pollinator reads file_scope from plan.yaml tasks:
```yaml
tasks:
  - id: "1.1"
    file_scope:
      owns:
        - "scripts/evo_db.py"
        - "tests/python/test_evo_db.py"
```

If a task has no file_scope, similarity defaults to 0.0 (skipped).

## Frontend Deliverables
- CLI outputs JSON with migration summary
- stderr logging: "Pollinator: found N completed tasks, M above threshold"
- stderr logging: "Pollinator: migrated K approaches from task {id} (similarity: 0.65)"

## Tests to Write (TDD-First)

### tests/python/test_evo_pollinator.py
- test_similarity_exact_file_match -- two tasks with same file in owns -> score includes +3
- test_similarity_shared_directory -- tasks with files in same directory but different names -> score includes +1
- test_similarity_task_type_match -- both tasks inferred as 'backend' -> score includes +2
- test_similarity_no_overlap -- completely unrelated file scopes -> returns 0.0
- test_pollinate_imports_from_similar -- create fixture with completed task above threshold having a population, verify approaches appear in target population
- test_pollinate_skips_dissimilar -- completed task below threshold -> no approaches migrated
- test_pollinate_filters_low_score -- completed task has approaches with test_pass_rate 0.3 and 0.7, only the 0.7 approach migrated
- test_pollinate_inspiration_island -- migrated approaches placed on island index num_islands-1 (default: island 2)
- test_pollinate_no_completed_tasks -- plan with all tasks pending -> no migration, no crash, returns {"migrated": 0}
- test_pollinate_missing_population -- completed task exists but has no .planning/evolution/ directory -> skip gracefully

## Test Dependency Graph

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | tests/python/test_evo_pollinator.py | -- | Create evo_pollinator.py. Import Approach and EvolutionDB from evo_db.py. Use tmp_path to create: (1) a fixture plan.yaml with 2 tasks (1.1 completed, 1.2 pending), (2) a fixture population at .planning/evolution/1.1/ with 3 approaches of varying scores, (3) empty target at .planning/evolution/1.2/. Call pollinate() and verify target population has migrated approaches. Reference scripts/learnings.py _compute_relevance_score for the +3/+1/+2 scoring pattern. |

Dispatch order:
- Wave 1: T1

## Key Links
- Similarity scoring reference: scripts/learnings.py _compute_relevance_score (lines 226-262)
- Task type inference reference: scripts/learnings.py _infer_task_type (lines 117-146)
- Depends on: scripts/evo_db.py (task 1.1, Approach and EvolutionDB)
- Consumer: hooks/stop-hook.sh (task 2.1, calls pollinator on first iteration)
- Plan structure: scripts/plan_utils.py (load_plan, find_task)

## Technical Notes
- Dependencies: scripts/evo_db.py (Approach, EvolutionDB) + scripts/plan_utils.py (load_plan) + stdlib
- The inspiration island is always the last island (index num_islands - 1) to keep migrated approaches separate from locally evolved ones
- Threshold default 0.3 is lenient -- even modest file scope overlap triggers pollination
- Only approaches with test_pass_rate >= 0.5 are migrated to avoid seeding with poor approaches
- The pollinator runs once (first iteration) and is idempotent -- re-running it adds duplicates but MAP-Elites grid handles this (same cell, same score = no replacement)
- If plan.yaml has no file_scope fields, pollination silently returns 0 migrations
- _infer_task_type is intentionally simple (file extension heuristic) -- it only needs to distinguish broad categories for the +2 bonus
