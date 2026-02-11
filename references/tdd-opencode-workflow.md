# TDD + Opencode MCP Concurrent Execution

## Overview
GSD-VGL uses a TDD-first workflow where tests are written before implementation. For tasks with multiple test files, implementation can be parallelized using opencode MCP agents.

## Workflow

### Phase 1: Test Writing (Sequential)
The executor agent writes ALL tests first, before any implementation:
1. Read task-{id}.md for test specifications
2. Create test files per the task's "Tests to Write" section
3. Run tests to confirm they fail (RED phase)
4. Commit test files

### Phase 2: Implementation (Concurrent)
For tasks with multiple independent test files:
1. Call `launch_opencode(mode="build", task="Make tests in {file} pass")` for each test file
2. Each opencode agent works independently on its test file's implementation
3. Call `wait_for_completion()` to collect results
4. Integrate any conflicting changes

For tasks with a single test file or tightly coupled tests:
1. Implement sequentially in the main context
2. Run tests after each change

### Phase 3: Verification (Sequential)
1. Run full test suite
2. Fix any integration issues from concurrent implementation
3. Verify must_haves are satisfied
4. Spawn verifier agent for independent validation

## When to Use Concurrent Execution
- Task has 2+ independent test files
- Test files target different modules/components
- File scopes don't overlap significantly

## When to Use Sequential Execution
- Single test file
- Tests are tightly coupled (shared state, ordering)
- Small task (< 3 test cases)

## opencode MCP API
```
launch_opencode(mode="build", task="Make tests in {file} pass")
  -> Returns: agent_id

wait_for_completion(agent_ids=[...])
  -> Returns: results per agent
```

## Error Handling
- If an opencode agent fails, retry once
- If retry fails, fall back to sequential implementation
- Always run full test suite after concurrent phase
