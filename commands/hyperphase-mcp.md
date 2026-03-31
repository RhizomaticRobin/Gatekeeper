---
description: "Hyperphase N via MCP — All operations through MCP tools only, no Task spawning"
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "AskUserQuestion", "mcp__plugin_gatekeeper_evolve-mcp__scout_hotspots", "mcp__plugin_gatekeeper_evolve-mcp__analyze_novelty", "mcp__plugin_gatekeeper_evolve-mcp__diagnose_failures", "mcp__plugin_gatekeeper_evolve-mcp__analyze_timing", "mcp__plugin_gatekeeper_evolve-mcp__fuse_scout_results", "mcp__plugin_gatekeeper_evolve-mcp__optimize_function", "mcp__plugin_gatekeeper_evolve-mcp__create_optimization_plan", "mcp__plugin_gatekeeper_evolve-mcp__profile_hotspots", "mcp__plugin_gatekeeper_evolve-mcp__extract_function", "mcp__plugin_gatekeeper_evolve-mcp__population_stats", "mcp__plugin_gatekeeper_evolve-mcp__population_sample", "mcp__plugin_gatekeeper_evolve-mcp__population_add", "mcp__plugin_gatekeeper_evolve-mcp__population_best", "mcp__plugin_gatekeeper_evolve-mcp__population_migrate", "mcp__plugin_gatekeeper_evolve-mcp__replace_function", "mcp__plugin_gatekeeper_evolve-mcp__revert_function", "mcp__plugin_gatekeeper_evolve-mcp__evaluate_correctness", "mcp__plugin_gatekeeper_evolve-mcp__evaluate_timing", "mcp__plugin_gatekeeper_evolve-mcp__check_novelty", "mcp__plugin_gatekeeper_evolve-mcp__set_llm_config", "mcp__plugin_gatekeeper_evolve-mcp__get_llm_config"]
---

# Hyperphase N — MCP-Only Version

All token generation through MCP tools. No Task spawning. The MCP server handles all LLM calls.

## Prerequisites

- Hyperphase 1 complete (all tasks VERIFICATION_PASS)
- `plan.yaml metadata.hyperphase: true`
- Evolve-MCP v2 server running

---

## Phase M1 — Discovery (MCP Only)

### Step 1: Agentic + Procedural Scout in Single Call

```
result = mcp__plugin_gatekeeper_evolve-mcp__scout_hotspots(
    source_dirs="{source_dirs}",
    module_path="",
    test_command="{test_command}",
    include_procedural=True,
    model="claude-sonnet-4-20250514"
)
```

This single call:
1. Reads source files
2. Analyzes algorithmic complexity
3. Detects anti-patterns
4. Optionally runs cProfile for validation
5. Returns combined results with reasoning

### Step 2: Parse Results

```python
candidates = result["candidates"]
procedural_validation = result.get("procedural_validation", [])

# Cross-validate
for cand in candidates:
    proc_match = find_in_procedural(cand, procedural_validation)
    if proc_match:
        cand["confidence"] = 0.95
        cand["baseline_ms"] = proc_match["baseline_ms"]
    else:
        cand["confidence"] = 0.5  # Agentic only
```

### Step 3: Select Top K

Select top K candidates by `confidence × (time_pct or estimated_score)`.

---

## Phase M2 — Planning (MCP Only)

### Step 1: Create Optimization Plan

```
plan = mcp__plugin_gatekeeper_evolve-mcp__create_optimization_plan(
    source_dirs="{source_dirs}",
    test_command="{test_command}",
    max_candidates=3,
    model="claude-sonnet-4-20250514"
)
```

This orchestrates:
1. Procedural profiling
2. Agentic analysis
3. Fusion of results
4. Strategy definition
5. Plan generation

### Step 2: Write Plan

Write `plan` to `.planning/hyperphase/plan.yaml`.

### Step 3: User Approval

Present plan summary. User approves by:
```bash
touch .planning/hyperphase/.ready
```

---

## Phase M3 — Execution (MCP Only)

For each candidate in plan:

### Step 1: Extract Function

```
function_code = mcp__plugin_gatekeeper_evolve-mcp__extract_function(
    file_path="{candidate.file}",
    function_name="{candidate.function}"
)
```

### Step 2: Initialize Population

```
db_path = ".planning/hyperphase/evolution/{candidate.function}/"
stats = mcp__plugin_gatekeeper_evolve-mcp__population_stats(db_path=db_path)
```

### Step 3: Run 5 Islands (Sequential or Parallel MCP Calls)

```
ISLAND_STRATEGIES = [
    "Vectorize with numpy/list comprehensions, eliminate Python for-loops",
    "Reduce allocations, use in-place operations, generators",
    "Memoize and precompute invariants, cache intermediate results",
    "Use fundamentally different data structures (set, deque, array)",
    "Novel algorithm, reduce complexity class, O(n) for O(n²)",
]

for island_id in range(5):
    # Get previous attempts from population
    sample = mcp__plugin_gatekeeper_evolve-mcp__population_sample(
        db_path=db_path,
        island_id=island_id
    )
    previous_attempts = json.dumps(sample.get("previous_codes", []))

    # Generate optimization via MCP
    opt_result = mcp__plugin_gatekeeper_evolve-mcp__optimize_function(
        function_code=function_code,
        analysis=json.dumps(candidate["agentic"]),
        strategy=ISLAND_STRATEGIES[island_id],
        previous_attempts=previous_attempts,
        island_id=island_id
    )

    if "error" not in opt_result:
        # Add to population
        mcp__plugin_gatekeeper_evolve-mcp__population_add(
            db_path=db_path,
            approach_json=json.dumps({
                "code": opt_result["optimized_code"],
                "explanation": opt_result["explanation"],
                "estimated_speedup": opt_result["estimated_speedup"],
                "island": island_id,
            })
        )
```

### Step 4: Migrate and Select Best

```
# Ring migration
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path, 0, 1)
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path, 1, 2)
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path, 2, 3)
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path, 3, 4)
mcp__plugin_gatekeeper_evolve-mcp__population_migrate(db_path, 4, 0)

# Get best
best = mcp__plugin_gatekeeper_evolve-mcp__population_best(db_path=db_path)
```

### Step 5: Procedural Validation

```
timing = mcp__plugin_gatekeeper_evolve-mcp__evaluate_timing(
    test_command="{test_command}",
    function_name="{candidate.function}",
    module_path="{candidate.file}",
    baseline_ms=candidate["procedural"]["baseline_ms"]
)

if timing["speedup_ratio"] < 1.2:
    # Skip this candidate
    continue
```

### Step 6: Agentic Timing Analysis (Optional)

```
analysis = mcp__plugin_gatekeeper_evolve-mcp__analyze_timing(
    before_code=function_code,
    after_code=best["code"],
    timing_result=json.dumps(timing)
)
```

### Step 7: Apply Patch

```
mcp__plugin_gatekeeper_evolve-mcp__replace_function(
    file_path="{candidate.file}",
    function_name="{candidate.function}",
    new_code=best["code"]
)
```

### Step 8: Incremental Verification

```
verify = mcp__plugin_gatekeeper_evolve-mcp__evaluate_correctness(
    test_command="{test_command}",
    source_dirs="{source_dirs}"
)

if verify["pass_rate"] < 1.0:
    # Agentic diagnosis
    diagnosis = mcp__plugin_gatekeeper_evolve-mcp__diagnose_failures(
        test_command="{test_command}",
        test_output=verify.get("output", ""),
        changed_files=json.dumps([candidate["file"]])
    )

    # Try fixes or revert
    if diagnosis["regression_risk"] == "high":
        mcp__plugin_gatekeeper_evolve-mcp__revert_function(
            file_path="{candidate.file}",
            function_name="{candidate.function}"
        )
```

---

## Phase M4 — Final Verification

### Step 1: Run Full Test Suite

```
result = mcp__plugin_gatekeeper_evolve-mcp__evaluate_correctness(
    test_command="{test_command}",
    source_dirs="{source_dirs}"
)
```

### Step 2: If Pass, Write Results

Write `.planning/hyperphase/results.md` with all optimization summaries.

### Step 3: If Fail, Rollback All

```
for patch in applied_patches:
    mcp__plugin_gatekeeper_evolve-mcp__revert_function(
        file_path=patch["file"],
        function_name=patch["function"]
    )
```

---

## Comparison: MCP-Only vs Task Spawning

| Aspect | Task Spawning | MCP-Only |
|--------|---------------|----------|
| Agent execution | Separate context | Same MCP server |
| State sharing | Hard | Easy (MCP-managed) |
| Token tracking | Per-agent | Centralized |
| Retry logic | Per-agent | Centralized |
| Model selection | In agent def | Per-tool config |
| Logging | Scattered | Centralized |
| Backend flexibility | Hardcoded Claude | Swappable |

---

## Configuration

```yaml
# In plan.yaml or MCP config
llm_config:
  default_model: "claude-sonnet-4-20250514"
  haiku_model: "claude-haiku-3-5-20241022"
  opus_model: "claude-opus-4-20250514"
  max_tokens: 4096
  temperature: 0.7
```

Or via MCP tool:

```
mcp__plugin_gatekeeper_evolve-mcp__set_llm_config(
    model="claude-sonnet-4-20250514",
    temperature=0.5
)
```

---

## Complete Example Session

```bash
# 1. Set up MCP server with v2
cd /home/user/gsd-vgl/evolve-mcp
python server_v2.py &

# 2. Run hyperphase (MCP-only)
/gatekeeper:hyperphase-mcp

# MCP calls made internally:
# - scout_hotspots() → finds candidates
# - create_optimization_plan() → makes plan
# - optimize_function() ×5 → generates optimizations
# - evaluate_timing() → validates speedup
# - replace_function() → applies changes
# - evaluate_correctness() → verifies tests
# - diagnose_failures() → if tests fail
# - revert_function() → if unfixable

# 3. Get token usage
mcp__plugin_gatekeeper_evolve-mcp__get_token_usage()
```
