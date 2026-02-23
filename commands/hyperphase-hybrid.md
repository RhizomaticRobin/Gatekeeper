---
description: "Hyperphase N (Hybrid) — Execute optimization plan with procedural ground truth + agentic understanding. Run after /gatekeeper:hyperphase-plan."
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)", "Bash(python3:*)", "Bash(cat:*)", "Read", "Task", "mcp__plugin_gatekeeper_evolve-mcp__profile_hotspots", "mcp__plugin_gatekeeper_evolve-mcp__extract_function", "mcp__plugin_gatekeeper_evolve-mcp__population_stats", "mcp__plugin_gatekeeper_evolve-mcp__population_migrate", "mcp__plugin_gatekeeper_evolve-mcp__population_best", "mcp__plugin_gatekeeper_evolve-mcp__replace_function", "mcp__plugin_gatekeeper_evolve-mcp__revert_function", "mcp__plugin_gatekeeper_evolve-mcp__evaluate_correctness", "mcp__plugin_gatekeeper_evolve-mcp__evaluate_timing"]
---

# Hyperphase N (Hybrid) — Execute Optimization Plan

Execute the optimization plan created by `/gatekeeper:hyperphase-plan`. Uses procedural ground truth + agentic understanding with cross-validation at every phase.

## Prerequisites

1. **Hyperphase 1 complete**: All tasks in plan.yaml have status `completed`
2. **Hyperphase plan exists**: `.planning/hyperphase/plan.yaml` must exist
3. **Plan is ready**: `.planning/hyperphase/.ready` file must exist (user approved)

## Check Prerequisites

```bash
# Check if plan exists
if [ ! -f .planning/hyperphase/plan.yaml ]; then
    echo "ERROR: No hyperphase plan found. Run /gatekeeper:hyperphase-plan first."
    exit 1
fi

# Check if plan is approved
if [ ! -f .planning/hyperphase/.ready ]; then
    echo "ERROR: Plan not approved. Review .planning/hyperphase/plan.yaml and run:"
    echo "  touch .planning/hyperphase/.ready"
    exit 1
fi
```

## Read Plan Configuration

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hyperphase_utils.py" .planning/hyperphase/plan.yaml --get config.test_command
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hyperphase_utils.py" .planning/hyperphase/plan.yaml --get config.source_dirs
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hyperphase_utils.py" .planning/hyperphase/plan.yaml --get execution_order
```

---

## Phase E1 — Pre-Execution Validation

### Step 1: Verify Tests Pass (Baseline)

Run the test suite to establish baseline:

```bash
{test_command}
```

If tests fail, abort: "Cannot optimize - baseline tests failing. Fix tests first."

### Step 2: Record Baseline Metrics

```
baseline_result = mcp__plugin_gatekeeper_evolve-mcp__evaluate_correctness(
    test_command="{test_command}",
    source_dirs="{source_dirs}"
)
```

Save to `.planning/hyperphase/baseline.json`:

```json
{
  "timestamp": "{now}",
  "test_pass_rate": 1.0,
  "test_count": {N},
  "duration_s": {duration}
}
```

---

## Phase E2 — Execute Optimization Plan

For each candidate in `execution_order` (run **sequentially**):

### Step 1: Load Candidate Plan

Read `.planning/hyperphase/candidates/{candidate_id}.md` for full context.

Verify `status == "pending"` in plan.yaml.

### Step 2: Extract Function

```
function_source = mcp__plugin_gatekeeper_evolve-mcp__extract_function(
    file_path="{candidate.file}",
    function_name="{candidate.function}"
)
```

### Step 3: Initialize Population DB

```
db_path = ".planning/hyperphase/evolution/{candidate.function}/"
mcp__plugin_gatekeeper_evolve-mcp__population_stats(db_path=db_path)
```

### Step 4: Spawn 5 Optimizer Tasks IN PARALLEL

Pass **plan context** to optimizers (from planning phase):

```
Task(subagent_type='gatekeeper:evo-optimizer', model='haiku', prompt="""
db_path: {db_path}
target_file: {candidate.file}
target_function: {candidate.function}
island_id: 0

=== FROM PLANNING PHASE ===
baseline_ms: {candidate.procedural.baseline_ms}
time_pct: {candidate.procedural.time_pct}
complexity_class: {candidate.agentic.complexity_class}
patterns_found: {candidate.agentic.patterns_found}
planned_strategies: {candidate.strategies}

island_strategy: "Vectorize with numpy/list comprehensions, eliminate Python for-loops, use faster builtins"
test_command: {test_command}
max_iterations: {config.max_iterations}
speedup_threshold: {config.speedup_threshold}
""")

# Islands 1-4 same as original, with planning context...
```

Wait for all 5 outputs.

### Step 5: Migrate and Select Winner

```
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path=db_path, src_island=0, dst_island=1)
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path=db_path, src_island=1, dst_island=2)
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path=db_path, src_island=2, dst_island=3)
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path=db_path, src_island=3, dst_island=4)
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path=db_path, src_island=4, dst_island=0)

best = mcp__plugin_gatekeeper_evolve-mcp__population_best(db_path=db_path)
```

### Step 6: Procedural Validation

**Measure actual speedup** before applying:

```
timing_result = mcp__plugin_gatekeeper_evolve-mcp__evaluate_timing(
    test_command="{test_command}",
    function_name="{candidate.function}",
    module_path="{candidate.file}",
    baseline_ms="{candidate.procedural.baseline_ms}"
)
```

Validate against plan expectations:

```python
planned_speedup = candidate.expected_outcome.estimated_speedup  # e.g., "4-6x"
actual_speedup = timing_result.speedup_ratio

if actual_speedup < config.speedup_threshold:
    update_plan_status(candidate.id, "skipped", f"Speedup {actual_speedup}x below threshold")
    continue

# Log comparison to plan
log_result({
    "candidate": candidate.id,
    "planned": planned_speedup,
    "actual": actual_speedup,
    "accuracy": compute_accuracy(planned_speedup, actual_speedup)
})
```

### Step 7: Apply Patch

```
mcp__plugin_gatekeeper_evolve-mcp__replace_function(
    file_path="{candidate.file}",
    function_name="{candidate.function}",
    new_code="{best.code}"
)
```

Update plan status:

```yaml
# In .planning/hyperphase/plan.yaml
candidates:
  - id: opt-001
    status: applied
    result:
      baseline_ms: 145.2
      optimized_ms: 28.3
      speedup: 5.13
      island: 2
      timestamp: "{now}"
```

Record for rollback tracking.

### Step 8: Incremental Verification

Run tests after each optimization:

```bash
{test_command}
```

If tests fail:
- Attempt agentic diagnosis
- Try quick fixes
- If unfixable, revert THIS optimization only and continue to next candidate

---

## Phase E3 — Final Verification

### Step 1: Run Full Test Suite

```bash
{test_command}
```

### Step 2: Compare to Baseline

```
final_result = mcp__plugin_gatekeeper_evolve-mcp__evaluate_correctness(
    test_command="{test_command}",
    source_dirs="{source_dirs}"
)

baseline = load_json(".planning/hyperphase/baseline.json")
```

### Step 3: If PASS

Write results to `.planning/hyperphase/results.md`:

```markdown
# Hyperphase N Results

## Summary
- **Candidates Planned**: {N}
- **Optimizations Applied**: {M}
- **Optimizations Skipped**: {N-M}
- **Total Speedup**: {aggregate}x
- **Test Status**: PASS

## Baseline vs Final
| Metric | Baseline | Final | Change |
|--------|----------|-------|--------|
| Test Pass Rate | 100% | 100% | ✓ |
| Tests Passed | {N} | {N} | ✓ |

## Per-Function Results

| Function | Baseline | Optimized | Speedup | vs Plan | Status |
|----------|----------|-----------|---------|---------|--------|
| cast_rays | 145.2ms | 28.3ms | 5.13x | 4-6x planned ✓ | applied |
| find_neighbors | 67.3ms | 31.2ms | 2.16x | 2-3x planned ✓ | applied |
| batch_process | 23.1ms | 23.1ms | 1.0x | 1.5-2x planned ✗ | skipped |

## Planning Accuracy

| Candidate | Planned | Actual | Accuracy |
|-----------|---------|--------|----------|
| opt-001 | 4-6x | 5.13x | 85% |
| opt-002 | 2-3x | 2.16x | 92% |
| opt-003 | 1.5-2x | 1.0x | Missed |
```

### Step 4: If FAIL

1. Revert ALL applied optimizations:
   ```
   for patch in applied_patches:
       mcp__plugin_gatekeeper_evolve-mcp__revert_function(
           file_path=patch.file,
           function_name=patch.function
       )
   ```

2. Re-run tests to confirm revert

3. Write failure report to `.planning/hyperphase/failure.md`:
   ```markdown
   # Hyperphase N Failure Report

   ## What Failed
   {diagnosis}

   ## What Was Reverted
   - {fn1} ({file1})
   - {fn2} ({file2})

   ## Recommendations
   - Fix: {suggested_fix}
   - Re-plan: /gatekeeper:hyperphase-plan
   ```

---

## Summary: Full Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  PLANNING PHASE (/gatekeeper:hyperphase-plan)               │
│                                                              │
│  P1: Discovery    → procedural + agentic scouts             │
│  P2: Strategy     → define approaches for each candidate    │
│  P3: Plan Gen     → create plan.yaml + candidate files      │
│  P4: Approval     → user reviews and approves               │
│  P5: Ready        → create .ready signal                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  EXECUTION PHASE (/gatekeeper:hyperphase-hybrid)            │
│                                                              │
│  E1: Validate     → verify baseline tests pass              │
│  E2: Execute      → for each candidate in plan:             │
│       - Extract function                                    │
│       - Run 5 island optimizers with plan context           │
│       - Procedurally validate speedup                       │
│       - Apply if validated                                  │
│       - Incremental test verification                       │
│  E3: Final        → full test suite, write results          │
└─────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
.planning/hyperphase/
├── plan.yaml           # Main plan file
├── .ready              # Approval signal
├── baseline.json       # Pre-execution test baseline
├── candidates/
│   ├── opt-001.md      # Candidate 1 details
│   ├── opt-002.md      # Candidate 2 details
│   └── ...
├── evolution/
│   ├── cast_rays/      # Population DB for function
│   ├── find_neighbors/
│   └── ...
├── results.md          # Final results (on success)
└── failure.md          # Failure report (on failure)
```

---

## Configuration

```yaml
# .planning/hyperphase/plan.yaml
config:
  test_command: "pytest tests/"
  source_dirs: "src/,lib/"
  max_candidates: 3
  speedup_threshold: 1.3
  island_count: 5
  max_iterations: 15
  require_incremental_verification: true
```
