---
task_id: "{task_id}"
task_name: "{task_name}"
phase: "{phase_id}"
status: pending
---

# Task {task_id}: {task_name}

## Goal
{goal derived from must_haves}

## Context
{relevant context from phase and project}

## Must-Haves
### Truths (User-Observable Behaviors)
- {truth_1}

### Artifacts (Files with Real Implementation)
- {artifact_1}

### Key Links (Critical Connections)
- {key_link_1}

## Deliverables
{backend and frontend deliverables}

## Tests to Write (Tester Agent — Phase 1)
{test files and what they test - written by the tester agent BEFORE executor begins}
NOTE: These test specifications are instructions for the **tester agent**, not the executor.
The tester writes comprehensive tests based on these specs, passes the `assess_tests` quality gate,
and then the executor receives the pre-written tests to implement against.

## Test Dependency Graph
Each test below has clear implementation guidance for the **executor agent** (Phase 2).
Tests with no dependencies on each other can be implemented in parallel; tests that depend on another
test's implementation must wait for that test to complete.

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | {test_file_1} | — | {what to implement, which files to create/modify, patterns to follow} |
| T2 | {test_file_2} | — | {implementation guidance for this test} |
| T3 | {test_file_3} | T1 | {this test requires T1's implementation to exist first} |

Dispatch order:
- Wave 1 (concurrent): T1, T2
- Wave 2 (after wave 1): T3

## Contract Specifications

### Function Contracts
| Function | Preconditions | Postconditions |
|----------|--------------|----------------|
| {module::function_name} | {formal precondition expression} | {formal postcondition expression} |

### Kani Harness Outlines (Rust only)
- **{harness_name}**: targets `{function}`, inputs: `{kani::any bounded}`, asserts: `{properties}`

### Verification Command
`{cargo prusti | cargo kani --harness X | crosshair check src/module.py}`

## Qualitative Verification
{Playwright visual checks or manual verification steps}

## Technical Notes
{constraints, dependencies, edge cases}
