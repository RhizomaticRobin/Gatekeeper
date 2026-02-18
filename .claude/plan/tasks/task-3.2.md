# Task 3.2: End-to-End Evolution Smoke Test

## Goal (from must_haves)
**Truths:**
- Fixture project at tests/fixtures/evo-project/ contains a plan.yaml, task files, source, tests, and pre-populated evolution data
- test_evo_db_add_and_sample verifies add -> sample roundtrip
- test_cascade_eval_stages verifies the 3-stage cascade evaluation pipeline
- test_prompt_builder verifies evolution context markdown contains all 5 sections
- test_pollination verifies cross-task approach migration from completed task to pending task
- test_full_pipeline verifies end-to-end flow: add approaches -> sample best -> build prompt -> verify evolution context

**Artifacts:**
- tests/e2e/evo-smoke-test.bats
- tests/fixtures/evo-project/ (fixture directory)

## Context
Tasks 1.1-1.3, 2.1-2.3, and 3.1 built and integrated the evolutionary intelligence engine. This task creates an end-to-end smoke test that exercises the full pipeline in a controlled fixture environment, verifying that all components work together.

The fixture project simulates a real Gatekeeper workspace with a plan, task files, source code, tests, and pre-populated evolution data. Each E2E test copies this fixture to a temp directory and exercises the evo scripts in sequence.

## Backend Deliverables

### Fixture Project: `tests/fixtures/evo-project/`

**`.claude/plan/plan.yaml`:**
```yaml
metadata:
  project: "evo-test-project"
  dev_server_command: "echo ok"
  dev_server_url: "http://localhost:3000"
  model_profile: "default"
phases:
  - id: 1
    name: "Core"
    tasks:
      - id: "1.1"
        name: "Index Module"
        status: "completed"
        depends_on: []
        file_scope:
          owns:
            - "src/index.py"
            - "tests/test_index.py"
        deliverables:
          backend: "src/index.py"
          frontend: ""
        tests:
          quantitative:
            command: "pytest tests/test_index.py -v"
          qualitative:
            criteria:
              - "Function works correctly"
        prompt_file: "tasks/task-1.1.md"
      - id: "1.2"
        name: "Helper Module"
        status: "pending"
        depends_on: ["1.1"]
        file_scope:
          owns:
            - "src/helper.py"
            - "tests/test_helper.py"
        deliverables:
          backend: "src/helper.py"
          frontend: ""
        tests:
          quantitative:
            command: "pytest tests/test_helper.py -v"
          qualitative:
            criteria:
              - "Helper functions work"
        prompt_file: "tasks/task-1.2.md"
```

**`.claude/plan/tasks/task-1.1.md`:**
Simple task description for the index module.

**`.claude/plan/tasks/task-1.2.md`:**
Simple task description for the helper module.

**`src/index.py`:**
```python
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
```

**`tests/test_index.py`:**
```python
from src.index import add, multiply

def test_add():
    assert add(2, 3) == 5

def test_multiply():
    assert multiply(3, 4) == 12

def test_add_negative():
    assert add(-1, 1) == 0  # This test passes
```

**`.planning/evolution/1.1/approaches.jsonl`:**
Pre-populated with 3 approaches showing improving scores:
```jsonl
{"id":"a1","prompt_addendum":"Focus on basic arithmetic","parent_id":null,"generation":0,"metrics":{"test_pass_rate":0.33,"complexity":10},"island":0,"feature_coords":[0,0],"task_id":"1.1","task_type":"backend","file_patterns":["src/index.py"],"artifacts":{"test_output":"1 passed, 2 failed","error_trace":""},"timestamp":1700000000,"iteration":1}
{"id":"a2","prompt_addendum":"Handle edge cases carefully","parent_id":"a1","generation":1,"metrics":{"test_pass_rate":0.67,"complexity":15},"island":1,"feature_coords":[3,1],"task_id":"1.1","task_type":"backend","file_patterns":["src/index.py"],"artifacts":{"test_output":"2 passed, 1 failed","error_trace":"AssertionError"},"timestamp":1700001000,"iteration":2}
{"id":"a3","prompt_addendum":"Implement all operations with type checking","parent_id":"a2","generation":2,"metrics":{"test_pass_rate":1.0,"complexity":20},"island":0,"feature_coords":[9,2],"task_id":"1.1","task_type":"backend","file_patterns":["src/index.py"],"artifacts":{"test_output":"3 passed","error_trace":""},"timestamp":1700002000,"iteration":3}
```

**`.planning/evolution/1.1/metadata.json`:**
```json
{
    "island_feature_maps": [{"(0, 0)": "a1", "(9, 2)": "a3"}, {"(3, 1)": "a2"}, {}],
    "islands": [["a1", "a3"], ["a2"], []],
    "best_id": "a3",
    "island_best_ids": ["a3", "a2", null],
    "config": {"num_islands": 3, "feature_dimensions": ["test_pass_rate", "complexity"], "feature_bins": 10}
}
```

### E2E Tests: `tests/e2e/evo-smoke-test.bats`

Each test:
1. Copies fixture to a temp directory
2. Sets PLUGIN_ROOT to the project root (for script access)
3. Runs evo scripts against the fixture
4. Asserts expected outcomes

## Frontend Deliverables
- Running `npx bats tests/e2e/evo-smoke-test.bats` shows all 5 tests passing
- Each test clearly named with descriptive output
- Temp directories cleaned up after each test

## Tests to Write (TDD-First)

### tests/e2e/evo-smoke-test.bats
- test_evo_db_add_and_sample -- copy fixture to tmp, add a new approach via `evo_db.py --add`, then sample via `evo_db.py --sample 0`, verify JSON output contains "parent" key with the newly added approach or an existing one
- test_cascade_eval_stages -- copy fixture to tmp, cd into it, run `evo_eval.py --evaluate "pytest tests/test_index.py -v"`, verify JSON output contains "test_pass_rate" and "stage" keys, and stage is 3 (all tests pass in fixture)
- test_prompt_builder -- copy fixture to tmp, run `evo_prompt.py --build .planning/evolution/1.1/ 1.1`, verify output contains all 5 section headers: "## Evolution Context", "## Parent Approach", "## What Went Wrong", "## Inspiration Approaches", "## Your Directive"
- test_pollination -- copy fixture to tmp, create empty target dir `.planning/evolution/1.2/`, run `evo_pollinator.py --pollinate .planning/evolution/1.2/ .claude/plan/plan.yaml 1.2`, verify JSON output shows "migrated" > 0 (task 1.1 is completed and similar)
- test_full_pipeline -- copy fixture to tmp, add 5 approaches with varying scores (0.2, 0.4, 0.6, 0.8, 1.0) via `evo_db.py --add`, get best via `evo_db.py --best` (verify score is 1.0), build prompt via `evo_prompt.py --build`, verify prompt contains "Parent Approach" and "Inspiration"

## Test Dependency Graph

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | tests/e2e/evo-smoke-test.bats | -- | Create the fixture project directory at tests/fixtures/evo-project/ with all files listed above. Create evo-smoke-test.bats. Each test uses `setup()` to copy fixture to a BATS_TEST_TMPDIR, sets PLUGIN_ROOT, and `teardown()` to clean up. Call evo scripts via `python3 "$PLUGIN_ROOT/scripts/evo_db.py" ...` and parse JSON output with python3 -c or jq. Follow the pattern from existing tests/e2e/smoke-test.bats if it exists, otherwise follow tests/bash/stop-hook.bats patterns for bats test structure. |

Dispatch order:
- Wave 1: T1

## Key Links
- Exercises: scripts/evo_db.py (task 1.1), scripts/evo_eval.py (task 1.2), scripts/evo_prompt.py (task 1.3), scripts/evo_pollinator.py (task 2.3)
- Fixture pattern: tests/bash/fixtures/ (existing fixture directory)
- Existing E2E pattern: tests/e2e/ (if exists)

## Technical Notes
- Each bats test should copy the fixture to a fresh tmp dir to ensure test isolation
- The fixture's pre-populated evolution data (approaches.jsonl + metadata.json) must be valid for evo_db.py to load
- test_cascade_eval_stages requires pytest to be installed and the fixture's test_index.py to be importable (add src/ to PYTHONPATH)
- The fixture tests are designed to have 3/3 passing (stage 3 full pass) so the cascade evaluation completes all stages
- test_pollination relies on task 1.1 being "completed" and task 1.2 being "pending" in the plan, with overlapping file_scope (both in src/)
- Use `run` command in bats to capture exit code and output, then assert with `assert_success` and `assert_output --partial`
- JSON parsing: prefer `python3 -c "import sys,json; ..."` over `jq` since jq may not be installed (though it is used in stop-hook.sh)
- The fixture approaches.jsonl uses simple feature_coords as lists -- evo_db.py should handle both tuple and list formats when loading
