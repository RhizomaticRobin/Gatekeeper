---
description: "Hyperphase N — evolutionary optimization of hot-spot functions for speed after Hyperphase 1 verification"
allowed-tools: ["Bash", "Write", "Read", "Task", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__extract_function", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__extract_bundle", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_stats", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_migrate", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_best", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__replace_function", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__revert_function", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__taichi_profile", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__taichi_analyze", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__benchmark_harness_gen"]
---

# Hyperphase N — Evolutionary Optimization

Run Hyperphase N to discover speed-optimized rewrites of hot-spot functions using MAP-Elites island-based optimization. Hyperphase 1 is the main Gatekeeper Pipeline (test → assess → execute → verify); Hyperphase N runs after all tasks pass verification.

## Prerequisites

- All tasks in plan.yaml must have status `completed` (VERIFICATION_PASS) — i.e. Hyperphase 1 is complete
- `plan.yaml metadata.hyperphase: true` (opt-in)

## Configuration

Read plan.yaml for:
- `test_command`: from the task test specs
- `source_dirs`: project source directories
- `metadata.hyperphase_candidates`: number of top-K candidates (default 3)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --get-metadata hyperphase
```

If not "true", inform the user that Hyperphase N is not enabled and exit.

---

## Phase S1 — Scout Identification

For each module directory in source_dirs, spawn an evo-scout Task in parallel:

```
Task(subagent_type='gatekeeper:evo-scout', model='haiku', prompt="""
module_path: {module}
test_command: {test_command}
source_dirs: {source_dirs}

YOUR JOB: Call profile_hotspots MCP tool with the parameters above.
Filter results: keep only functions with complexity > 5 AND test_count >= 1.
Output: SCOUT_DONE:{module}:{json_array_of_candidates}
""")
```

Collect all `SCOUT_DONE` outputs. Parse the JSON arrays. Merge all candidates into a single list. Rank by `score` descending. Select top K (from metadata.hyperphase_candidates, default 3).

If no candidates found, report "No optimization candidates identified" and exit.

---

## Phase S2 — Island Optimization

For each selected candidate (run **sequentially** — tests share the filesystem):

### Step 0: Detect Target Type (MANDATORY)

ALWAYS run this FIRST for every candidate to determine GPU vs CPU optimization:

```
analysis = mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__taichi_analyze(
    file_path="{candidate.file}",
    function_name="{candidate.function}"
)
is_taichi = analysis.is_ti_kernel or analysis.is_ti_func
```

This determines which island strategies and timing tools to use below.

### Step 1: Extract Function

**If Taichi** (use `extract_bundle` for kernel + dependencies):
```
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__extract_bundle(
    file_path="{candidate.file}",
    function_name="{candidate.function}"
)
```

**If plain Python**:
```
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__extract_function(
    file_path="{candidate.file}",
    function_name="{candidate.function}"
)
```

### Step 2: Initialize Population DB

```
db_path = ".planning/evolution/hyperphase/{candidate.function}/"
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_stats(db_path=db_path)
```

If empty, that's expected — optimizers will seed it.

### Step 3: Spawn 5 Optimizer Tasks IN PARALLEL

Use the `is_taichi` flag from Step 0 to select strategies. **Taichi GPU strategies are the primary case** — only fall back to generic Python strategies if the target is NOT a Taichi kernel.

**If `is_taichi = True`** (primary — GPU kernel optimization):

```
Task(subagent_type='gatekeeper:evo-optimizer', model='haiku', prompt="""
db_path: {db_path}
target_file: {candidate.file}
target_function: {candidate.function}
island_id: 0
island_strategy: "Reduce register pressure: minimize local variables, reuse temporaries, use ti.cast to smaller types, share computations via ti.block_local"
baseline_ms: {candidate.baseline_ms}
test_command: {test_command}
max_iterations: 50
speedup_threshold: 1.5
""")

Task(subagent_type='gatekeeper:evo-optimizer', model='haiku', prompt="""
db_path: {db_path}
target_file: {candidate.file}
target_function: {candidate.function}
island_id: 1
island_strategy: "Eliminate thread divergence: replace conditionals with ti.select() (branchless), use ti.static() for compile-time branching, flatten conditional loops"
baseline_ms: {candidate.baseline_ms}
test_command: {test_command}
max_iterations: 50
speedup_threshold: 1.5
""")

Task(subagent_type='gatekeeper:evo-optimizer', model='haiku', prompt="""
db_path: {db_path}
target_file: {candidate.file}
target_function: {candidate.function}
island_id: 2
island_strategy: "Improve memory coalescing: restructure field accesses for sequential innermost-dimension access, use SoA layout (separate ti.fields instead of Vector.field), tile with ti.block_dim"
baseline_ms: {candidate.baseline_ms}
test_command: {test_command}
max_iterations: 50
speedup_threshold: 1.5
""")

Task(subagent_type='gatekeeper:evo-optimizer', model='haiku', prompt="""
db_path: {db_path}
target_file: {candidate.file}
target_function: {candidate.function}
island_id: 3
island_strategy: "Reduce kernel dispatch count: fuse multiple kernel bodies into one @ti.kernel with inner ti.static loops, eliminate Python-side for-loops that call kernels repeatedly"
baseline_ms: {candidate.baseline_ms}
test_command: {test_command}
max_iterations: 50
speedup_threshold: 1.5
""")

Task(subagent_type='gatekeeper:evo-optimizer', model='opus', prompt="""
db_path: {db_path}
target_file: {candidate.file}
target_function: {candidate.function}
island_id: 4
island_strategy: "Algorithmic reduction: replace O(n) scans with spatial hashing (ti.field-based hash grid), add early-exit conditions, precompute invariants outside parallel loops into scalar fields"
baseline_ms: {candidate.baseline_ms}
test_command: {test_command}
max_iterations: 50
speedup_threshold: 1.5
""")
```

**If `is_taichi = False`** (fallback — plain Python optimization):

```
Task(subagent_type='gatekeeper:evo-optimizer', model='haiku', prompt="""
... island_id: 0, island_strategy: "Vectorize with numpy/list comprehensions, eliminate Python for-loops, use faster builtins" ...
""")
Task(... island_id: 1, island_strategy: "Reduce allocations, use in-place operations, generators, eliminate unnecessary copies" ...)
Task(... island_id: 2, island_strategy: "Memoize and precompute invariants, eliminate redundant computation, cache intermediate results" ...)
Task(... island_id: 3, island_strategy: "Use fundamentally different data structures (set for O(1) lookup, deque vs list, array vs dict), optimize memory layout" ...)
Task(subagent_type='gatekeeper:evo-optimizer', model='opus', ... island_id: 4, island_strategy: "Novel algorithm, reduce complexity class, O(n log n) or O(n) replacement for O(n²), mathematical reformulation" ...)
```

Wait for all 5 outputs.

**IMPORTANT**: When `is_taichi = True`, the optimizer agents will automatically use `mode="taichi"` for `evolution_prompt` and `taichi_profile` for timing (instead of `evaluate_timing` which does NOT handle GPU synchronization). This is handled in the evo-optimizer agent's Step 0 auto-detection.

### Step 4: Migrate and Select Winner

```
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_migrate(db_path=db_path, src_island=0, dst_island=1)
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_migrate(db_path=db_path, src_island=1, dst_island=2)
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_migrate(db_path=db_path, src_island=2, dst_island=3)
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_migrate(db_path=db_path, src_island=3, dst_island=4)
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_migrate(db_path=db_path, src_island=4, dst_island=0)
```

```
best = mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__population_best(db_path=db_path)
```

### Step 5: Apply Patch (if speedup meets threshold)

If `best.metrics.speedup_ratio >= 1.3`:
```
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__replace_function(
    file_path="{candidate.file}",
    function_name="{candidate.function}",
    new_code="{best.code}"
)
```

Record the patch for Phase S3 rollback tracking.

If speedup < 1.3, skip this candidate (not worth the risk).

---

## Phase S3 — Final Verification

Run the full test suite:
```bash
{test_command}
```

**If tests PASS:**
- Write `hyperphase-results.md` with per-function speedup summary:
  ```markdown
  # Hyperphase N Results

  | Function | File | Baseline (ms) | Optimized (ms) | Speedup | Island |
  |----------|------|---------------|----------------|---------|--------|
  | {fn} | {file} | {baseline_ms} | {new_ms} | {speedup}x | {island} |
  ```

**If tests FAIL:**
- Revert ALL patched functions:
  ```
  mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__revert_function(file_path="{file}", function_name="{fn}")
  ```
  for each patched file.
- Re-run tests to confirm revert success.
- Report which patches were reverted.

---

## Integration with Team Orchestrator

This command can be run:
- **Standalone:** `/gatekeeper:hyperphase` (user manually triggers after Hyperphase 1 completes)
- **Automatic:** From team-orchestrator Section 8 when `metadata.hyperphase: true`
