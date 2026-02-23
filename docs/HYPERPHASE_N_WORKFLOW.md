# Hyperphase N — Complete Workflow

## Overview

Hyperphase N is a **two-phase** optimization system:

1. **Planning Phase** (`/gatekeeper:hyperphase-plan`) — Discover, analyze, plan, get approval
2. **Execution Phase** (`/gatekeeper:hyperphase-hybrid`) — Execute plan with validation

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         HYPERPHASE N WORKFLOW                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  PLANNING PHASE                                                      │  │
│  │  /gatekeeper:hyperphase-plan                                         │  │
│  │                                                                      │  │
│  │  P1 ──► P2 ──► P3 ──► P4 ──► P5                                     │  │
│  │  │     │      │      │      │                                       │  │
│  │  │     │      │      │      └─► .ready signal                       │  │
│  │  │     │      │      └─► User approval                              │  │
│  │  │     │      └─► plan.yaml + candidate files                       │  │
│  │  │     └─► Strategy definition                                       │  │
│  │  └─► Discovery (procedural + agentic)                                │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                      │
│                                    ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  EXECUTION PHASE                                                     │  │
│  │  /gatekeeper:hyperphase-hybrid                                       │  │
│  │                                                                      │  │
│  │  E1 ──► E2 ──► E3                                                   │  │
│  │  │      │      │                                                    │  │
│  │  │      │      └─► Final verification + results.md                  │  │
│  │  │      └─► Execute plan (5 islands, validation, apply)             │  │
│  │  └─► Baseline validation                                             │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Phase-by-Phase Detail

### PLANNING PHASE: `/gatekeeper:hyperphase-plan`

#### P1: Discovery
- Spawn **procedural scout** (profile_hotspots) — ground truth timing
- Spawn **agentic scout** (hotspot-scout) — code understanding
- Cross-validate results

#### P2: Strategy Definition
- For each candidate, read function source
- Generate 2-3 optimization approaches
- Estimate speedup and risk for each

#### P3: Plan Generation
- Write `.planning/hyperphase/plan.yaml` (main plan)
- Write `.planning/hyperphase/candidates/{id}.md` (detail files)

#### P4: User Approval
- Present summary table
- User reviews plan files
- User can modify, skip candidates, or cancel

#### P5: Ready Signal
- `touch .planning/hyperphase/.ready`
- Signals execution phase can proceed

---

### EXECUTION PHASE: `/gatekeeper:hyperphase-hybrid`

#### E1: Pre-Execution Validation
- Verify baseline tests pass
- Record baseline metrics to `baseline.json`

#### E2: Execute Plan
For each candidate in `execution_order`:

| Step | Action | Validation |
|------|--------|------------|
| 1 | Load candidate plan | Verify status=pending |
| 2 | Extract function | Get source code |
| 3 | Init population DB | Prepare for evolution |
| 4 | Spawn 5 optimizers | Pass plan context |
| 5 | Migrate, select winner | Cross-island sharing |
| 6 | **Procedural validation** | Measure actual speedup |
| 7 | Apply patch | Only if validated |
| 8 | Incremental test | Catch regressions early |

#### E3: Final Verification
- Run full test suite
- Compare to baseline
- Write `results.md` (success) or `failure.md` (rollback)

---

## Key Design Principles

### 1. Hybrid Cross-Validation

Every decision uses both:

| Source | Provides | Validated By |
|--------|----------|--------------|
| Procedural | Exact timing | N/A (ground truth) |
| Agentic | Why slow, how to fix | Procedural timing |

**Example:**
```
Agent claims: "This will be 5x faster"
Procedural measures: "Actually 3.2x faster"
Decision: Apply (passes 1.3x threshold) but log discrepancy
```

### 2. Planning Before Execution

```
No plan → Run /gatekeeper:hyperphase-plan first
Plan exists but not approved → Review and approve
Plan approved → Run /gatekeeper:hyperphase-hybrid
```

### 3. Incremental Safety

- Test after EACH optimization (not just at end)
- If one fails, only revert that one
- Continue with remaining candidates

### 4. Measurable Outcomes

| Metric | Recorded In |
|--------|-------------|
| Planned speedup | plan.yaml |
| Actual speedup | results.md |
| Planning accuracy | results.md (comparison) |

---

## File Structure

```
.planning/hyperphase/
├── plan.yaml              # Main plan (from planning phase)
├── .ready                 # Approval signal
├── baseline.json          # Pre-execution baseline
│
├── candidates/
│   ├── opt-001.md         # Candidate 1 full analysis
│   ├── opt-002.md         # Candidate 2 full analysis
│   └── ...
│
├── evolution/
│   ├── cast_rays/
│   │   └── population.db  # MAP-Elites DB for this function
│   └── ...
│
├── results.md             # Final results (success)
└── failure.md             # Failure report (with rollback)
```

---

## Commands Reference

| Command | Purpose | When to Run |
|---------|---------|-------------|
| `/gatekeeper:hyperphase-plan` | Discover + plan optimizations | First, after Hyperphase 1 |
| `/gatekeeper:hyperphase-hybrid` | Execute the plan | After plan is approved |
| `/gatekeeper:hyperphase` | Procedural-only (no planning) | Quick iteration |

---

## Configuration

In main `plan.yaml`:

```yaml
metadata:
  hyperphase: true                    # Enable Hyperphase N
  hyperphase_mode: hybrid             # "procedural" | "hybrid"
  hyperphase_candidates: 3            # Max candidates to optimize
  hyperphase_auto_plan: false         # If true, auto-generate plan
```

In `.planning/hyperphase/plan.yaml`:

```yaml
config:
  test_command: "pytest tests/"
  source_dirs: "src/,lib/"
  max_candidates: 3
  speedup_threshold: 1.3              # Minimum speedup to apply
  island_count: 5
  max_iterations: 15
  require_incremental_verification: true
```

---

## Comparison: Procedural vs Hybrid

| Aspect | Procedural Only | Hybrid (Planning + Execution) |
|--------|-----------------|-------------------------------|
| Hotspot ID | profile_hotspots only | profile_hotspots + agent analysis |
| Strategy | None (optimizer figures it out) | Pre-planned strategies per candidate |
| User control | None (runs automatically) | Review plan, modify, approve |
| Speedup estimation | None (discover at runtime) | Planned estimates, validated at runtime |
| Safety | Test at end only | Test after each optimization |
| Recovery | Rollback all if fail | Incremental rollback |

---

## Example Session

```bash
# 1. Run planning phase
$ /gatekeeper:hyperphase-plan

# Output:
# Found 12 candidates, selected 3 for optimization
# Plan written to .planning/hyperphase/plan.yaml
# Review and approve: touch .planning/hyperphase/.ready

# 2. Review the plan
$ cat .planning/hyperphase/candidates/opt-001.md

# 3. Approve
$ touch .planning/hyperphase/.ready

# 4. Execute
$ /gatekeeper:hyperphase-hybrid

# Output:
# E1: Baseline tests pass ✓
# E2: Optimizing opt-001 (cast_rays)...
#     Island 2 winner: 5.13x speedup (planned: 4-6x) ✓
#     Tests pass ✓
# E2: Optimizing opt-002 (find_neighbors)...
#     Island 0 winner: 2.16x speedup (planned: 2-3x) ✓
#     Tests pass ✓
# E2: Optimizing opt-003 (batch_process)...
#     No approach met 1.3x threshold, skipping
# E3: Final verification pass ✓
# Results written to .planning/hyperphase/results.md
```

---

*Document created: 2026-02-23*
