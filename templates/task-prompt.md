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
Each test below becomes a single Task subagent dispatch by the **executor agent** (Phase 2).
Tests with no dependencies on each other run concurrently; tests that depend on another
test's implementation run after that test's agent completes.

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | {test_file_1} | — | {what to implement, which files to create/modify, patterns to follow} |
| T2 | {test_file_2} | — | {implementation guidance for this test} |
| T3 | {test_file_3} | T1 | {this test requires T1's implementation to exist first} |

Dispatch order:
- Wave 1 (concurrent): T1, T2
- Wave 2 (after wave 1): T3

## Sanctioned Mocks & Stubs
{List of explicitly allowed mocks/stubs for this task, or "None" if all code must be real.
Each entry should specify WHAT is mocked, WHY it must be mocked, and WHAT the mock should return.
Any mock or stub NOT listed here is a violation — the quibbler will flag it.}

- `{module_or_function}` — {reason it must be mocked, e.g., "external API not available in test env"} → returns {what the mock returns}

## Qualitative Verification
{Playwright visual checks or manual verification steps}

## Technical Notes
{constraints, dependencies, edge cases}
