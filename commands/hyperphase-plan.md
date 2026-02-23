---
description: "Hyperphase N Planning — Discover optimization candidates, propose strategies, get user approval before running optimization loop."
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)", "Bash(python3:*)", "Read", "Task", "mcp__plugin_gatekeeper_evolve-mcp__profile_hotspots"]
---

# Hyperphase N Planning

Planning phase for evolutionary optimization. Discovers candidates, proposes optimization strategies, estimates potential speedup, and creates a plan for user approval.

## When to Run

Run this BEFORE `/gatekeeper:hyperphase` or `/gatekeeper:hyperphase-hybrid`.

```
/gatekeeper:hyperphase-plan    → Creates .planning/hyperphase/plan.yaml
/gatekeeper:hyperphase         → Executes the plan
```

## Prerequisites

- Hyperphase 1 complete (all tasks VERIFICATION_PASS)
- `plan.yaml metadata.hyperphase: true`

---

## Phase P1 — Discovery

### Step 1: Read Configuration

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --get-metadata hyperphase
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --get-metadata hyperphase_candidates
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --get test_command
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --get source_dirs
```

### Step 2: Spawn Parallel Scouts

For each module in source_dirs, spawn procedural + agentic scouts:

```
Task(subagent_type='gatekeeper:evo-scout', model='haiku', prompt="""
module_path: {module}
test_command: {test_command}
source_dirs: {source_dirs}

YOUR JOB: Call profile_hotspots MCP tool.
Filter: complexity > 5 AND test_count >= 1.
Output: SCOUT_DONE:procedural:{module}:{json}
""")

Task(subagent_type='gatekeeper:hotspot-scout', model='sonnet', prompt="""
source_dirs: {source_dirs}
module_path: {module}

YOUR JOB:
1. Read source files
2. Identify O(n²)+ patterns, anti-patterns
3. Provide optimization strategies for each
Output: SCOUT_DONE:agentic:{module}:{json}
""")
```

### Step 3: Cross-Validate and Rank

Collect all scout outputs. Cross-validate:

```python
candidates = cross_validate(procedural_results, agentic_results)
candidates.sort(key=lambda c: (c.time_pct or 0) * c.confidence, reverse=True)
```

---

## Phase P2 — Strategy Definition

For each top candidate, define optimization strategy:

### Step 1: Read Function Source

```
mcp__plugin_gatekeeper_evolve-mcp__extract_function(
    file_path="{candidate.file}",
    function_name="{candidate.function}"
)
```

### Step 2: Generate Strategy Document

For each candidate, create a strategy:

```
Task(subagent_type='gatekeeper:strategy-planner', model='sonnet', prompt="""
function_source: {extracted_function}
agentic_analysis: {candidate.agentic}
procedural_timing: {candidate.procedural}

YOUR JOB:
1. Analyze the function for optimization opportunities
2. Propose 2-3 specific optimization approaches
3. Estimate speedup for each approach
4. Identify risks (may break tests, edge cases)
5. Recommend which approach to try first

Output: STRATEGY_DONE:{json_strategy}
""")
```

Strategy output format:

```json
{
  "function": "cast_rays",
  "file": "observation_kernels.py",
  "approaches": [
    {
      "name": "vectorize_rays",
      "description": "Vectorize ray calculations using numpy",
      "estimated_speedup": "3-5x",
      "risk": "medium",
      "risk_details": "May change float accumulation order",
      "implementation_complexity": "medium"
    },
    {
      "name": "precompute_trig",
      "description": "Precompute sin/cos lookup table",
      "estimated_speedup": "1.5-2x",
      "risk": "low",
      "risk_details": "Minor precision loss acceptable",
      "implementation_complexity": "easy"
    }
  ],
  "recommended_order": ["precompute_trig", "vectorize_rays"],
  "combined_potential": "5-8x if both succeed"
}
```

---

## Phase P3 — Plan Generation

### Step 1: Create Hyperphase Plan Directory

```bash
mkdir -p .planning/hyperphase
```

### Step 2: Write Plan File

Write `.planning/hyperphase/plan.yaml`:

```yaml
# Hyperphase N Optimization Plan
# Generated: {timestamp}
# Based on: .claude/plan/plan.yaml (Hyperphase 1)

metadata:
  hyperphase_1_plan: .claude/plan/plan.yaml
  discovery_method: hybrid  # procedural + agentic
  total_candidates_found: {N}
  candidates_selected: {K}

config:
  test_command: {test_command}
  source_dirs: {source_dirs}
  max_candidates: {K}
  speedup_threshold: 1.3
  island_count: 5
  max_iterations: 15

candidates:
  - id: "opt-001"
    function: "cast_rays"
    file: "observation_kernels.py"
    line_range: [234, 312]
    status: pending

    procedural:
      baseline_ms: 145.2
      time_pct: 42.3
      call_count: 1000

    agentic:
      complexity_class: "O(n*m*k)"
      patterns_found:
        - "nested_loop"
        - "redundant_trig"
        - "dynamic_dispatch"
      reasoning: "Triple nested loop with 3072 trig calls per agent"

    validation:
      confidence: 0.95
      status: validated

    strategies:
      - name: "precompute_trig"
        estimated_speedup: "1.5-2x"
        risk: low
        priority: 1
      - name: "vectorize_rays"
        estimated_speedup: "3-5x"
        risk: medium
        priority: 2

    expected_outcome:
      estimated_speedup: "4-6x combined"
      confidence: 0.85

  - id: "opt-002"
    function: "find_neighbors"
    file: "spatial_kernels.py"
    # ... similar structure

execution_order:
  - opt-001  # Highest impact
  - opt-002
  - opt-003

rollback_plan:
  - Each optimization creates .bak_{timestamp} backup
  - If tests fail, revert all functions in reverse order
  - If partial success, keep passing optimizations, report failures

success_criteria:
  minimum_speedup: 1.3x per function
  all_tests_must_pass: true
  max_regressions: 0
```

### Step 3: Write Candidate Detail Files

For each candidate, write `.planning/hyperphase/candidates/{id}.md`:

```markdown
# Optimization Candidate: opt-001

## Function: cast_rays
**File**: observation_kernels.py
**Lines**: 234-312

## Current Performance
- **Baseline**: 145.2ms
- **% of Runtime**: 42.3%
- **Complexity**: O(n*m*k)

## Problem Analysis
Triple nested loop with:
- 3072 sin/cos calls per agent per step
- Dynamic dispatch in innermost loop
- List appends in hot path

## Proposed Optimizations

### Strategy 1: Precompute Trig Tables (Priority: 1)
- **Description**: Cache sin/cos values for common angles
- **Estimated Speedup**: 1.5-2x
- **Risk**: Low
- **Implementation**: Easy

### Strategy 2: Vectorize Ray Calculations (Priority: 2)
- **Description**: Process all rays simultaneously with numpy
- **Estimated Speedup**: 3-5x
- **Risk**: Medium (float precision)
- **Implementation**: Medium

## Expected Outcome
**Combined Speedup**: 4-6x
**Confidence**: 85%

## Risks
- Float precision may change slightly
- May need to adjust test tolerances
```

---

## Phase P4 — User Approval

Present the plan to the user for approval:

```markdown
# Hyperphase N Optimization Plan

## Summary
- **Candidates Found**: {N}
- **Candidates Selected**: {K}
- **Estimated Total Speedup**: {X}x - {Y}x
- **Estimated Time**: {hours}h (based on {K} candidates × 15 iterations)

## Candidates

| ID | Function | File | Current | Est. Speedup | Confidence |
|----|----------|------|---------|--------------|------------|
| opt-001 | cast_rays | observation_kernels.py | 145.2ms | 4-6x | 85% |
| opt-002 | find_neighbors | spatial_kernels.py | 67.3ms | 2-3x | 78% |
| opt-003 | batch_process | core.py | 23.1ms | 1.5-2x | 72% |

## Execution Plan
1. Optimize `cast_rays` (highest impact)
2. Optimize `find_neighbors`
3. Optimize `batch_process`

## Next Steps
- Review: `.planning/hyperphase/plan.yaml`
- Review: `.planning/hyperphase/candidates/*.md`
- Approve to begin optimization: `/gatekeeper:hyperphase --execute`
- Modify plan: Edit `.planning/hyperphase/plan.yaml`
```

### User Options

1. **Approve as-is**: `/gatekeeper:hyperphase` proceeds with plan
2. **Modify candidates**: Edit `.planning/hyperphase/plan.yaml`
3. **Skip specific candidates**: Set `status: skipped` in plan
4. **Add custom candidates**: Add new entries to plan
5. **Cancel**: Delete `.planning/hyperphase/plan.yaml`

---

## Phase P5 — Ready Signal

Create ready signal file when plan is approved:

```bash
touch .planning/hyperphase/.ready
```

The execution command checks for this file before proceeding.
