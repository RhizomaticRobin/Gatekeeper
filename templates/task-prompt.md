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

## Tests to Write (TDD-First)
{test files and what they test - written BEFORE implementation}

## Test Dependency Graph
Each test below becomes a single opencode agent dispatch. Tests with no
dependencies on each other run concurrently; tests that depend on another
test's implementation run after that test's agent completes.

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | {test_file_1} | — | {what to implement, which files to create/modify, patterns to follow} |
| T2 | {test_file_2} | — | {implementation guidance for this test} |
| T3 | {test_file_3} | T1 | {this test requires T1's implementation to exist first} |

Dispatch order:
- Wave 1 (concurrent): T1, T2
- Wave 2 (after wave 1): T3

## Qualitative Verification
{Playwright visual checks or manual verification steps}

## Technical Notes
{constraints, dependencies, edge cases}
