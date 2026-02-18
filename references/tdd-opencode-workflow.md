# TDD + Opencode MCP Concurrent Execution

## Overview
Gatekeeper uses a TDD-first workflow where tests are written before implementation. For tasks with multiple test files, implementation can be parallelized using opencode MCP agents.

## Workflow

### Phase 1: Test Writing (Sequential)
The executor agent writes ALL tests first, before any implementation:
1. Read task-{id}.md for test specifications
2. Create test files per the task's "Tests to Write" section
3. Run tests to confirm they fail (RED phase)
4. Commit test files

### Phase 2: Implementation (Concurrent, Wave-Based with Session Continuations)
The executor reads the **Test Dependency Graph** from the task prompt and dispatches agents in waves:

1. **1 test = 1 opencode agent.** Each agent receives exactly one test file plus its guidance.
2. **Wave dispatch.** Tests with no dependencies run concurrently (wave 1). Tests depending on prior tests wait for those agents to finish (wave 2+).
3. **Guidance per agent.** The task prompt includes specific implementation guidance for each test — which files to create/modify, patterns to follow, approach to take.
4. **Session continuation for dependent tests.** When a test depends on a prior test, the executor continues the prior agent's session instead of spawning a new agent. The prior agent already has context about the code it wrote. If a test has multiple dependencies, continue the session of the most significant dependency's agent and instruct it to review the other dependencies' work first.

```
# Wave 1 (fresh agents — T1 and T2 have no dependencies)
launch_opencode(task="Make test pass: tests/auth.test.ts\n\nGUIDANCE:\nCreate src/auth/middleware.ts...")
launch_opencode(task="Make test pass: tests/db.test.ts\n\nGUIDANCE:\nCreate src/db/schema.ts...")
wait_for_completion()
# Record: agentMap["T1"] = sess-abc, agentMap["T2"] = sess-def

# Wave 2 (T3 depends on T1 — continue T1's session)
launch_opencode(sessionId="sess-abc", task="Now make this next test pass: tests/session.test.ts\n\nGUIDANCE:\n...")
wait_for_completion()

# Wave 3 (T5 depends on T1 and T3 — continue most significant, review others)
launch_opencode(sessionId="sess-abc", task="Now make this next test pass: tests/flow.test.ts\n\nREVIEW FIRST:\nThis also depends on T2's work. Read files from T2 guidance before implementing.\n\nGUIDANCE:\n...")
wait_for_completion()
```

For tasks with a single test:
- Implement directly in the executor context, no agent needed

### Phase 3: Verification (Sequential)
1. Run full test suite
2. Fix any integration issues from concurrent implementation
3. Verify must_haves are satisfied
4. Spawn verifier agent for independent validation

## Test Dependency Graph Format

Each task-{id}.md includes a test dependency graph:

```
| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | tests/auth.test.ts | — | Create src/auth/middleware.ts with JWT validation... |
| T2 | tests/db.test.ts | — | Create src/db/schema.ts with User model... |
| T3 | tests/session.test.ts | T1 | Import auth middleware, add session management... |
```

The planner (/quest) generates this graph. The executor follows it exactly.

## opencode MCP API

**IMPORTANT:** Always use these MCP tools. The `opencode` CLI binary is NOT on PATH — calling it from bash will fail. All agent dispatch MUST go through the MCP tools below.

```
# Fresh agent (wave 1 tests, no dependencies)
launch_opencode(task="Make test pass: {file}\n\nGUIDANCE:\n{guidance}")
  -> Returns: { taskId, sessionId, status: "working" }

# Batch launch (multiple independent tests in one call — preferred for Wave 1)
launch_opencode(tasks=[
  {type: "new", task: "Make test pass: tests/auth.test.ts\n\nGUIDANCE:\n..."},
  {type: "new", task: "Make test pass: tests/db.test.ts\n\nGUIDANCE:\n..."},
])
  -> Returns: { results: [{taskId, sessionId, status}], count: N }

# Continue session (wave 2+ tests, has dependencies)
launch_opencode(sessionId="{prior_sessionId}", task="Now make this next test pass: {file}\n\nGUIDANCE:\n{guidance}")
  -> Returns: { taskId, sessionId, status: "working" }

# Wait for all agents in a wave
wait_for_completion(taskIds=[...])
  -> Returns: results per task (10 minute timeout)

# Check running agents
opencode_sessions(status="active")
  -> Returns: { sessions: [...], total: N }
```

### Maximizing Concurrency
- Use `launch_opencode(tasks=[...])` for Wave 1 to batch-launch all independent tests in a single call
- Never launch agents one-at-a-time with waits between them when they have no dependencies
- Call `wait_for_completion()` once per wave, not once per agent

## Agent Questions During Execution

gk-builder agents can ask questions when they hit ambiguity. The opencode MCP
server detects questions automatically (text ending with "?" + 30s idle) and
sets the task status to `input_required`.

### When agents SHOULD ask
- Test expectation is ambiguous (unclear what correct behavior should be)
- Required dependency or import path cannot be determined from context
- Multiple valid approaches exist with meaningfully different tradeoffs

### When agents should NOT ask
- Answer is inferable from existing code patterns
- Pure implementation detail (pick simplest approach)
- Syntax/runtime errors (debug it)

### Parent executor handling
After calling wait_for_completion(), check for input_required tasks:

1. If a result has status "input_required":
   - Read accumulatedText to find the question (look at the end)
   - Formulate answer from task context (task prompt, test files, conventions)
   - Continue the session: launch_opencode(sessionId=result.sessionId, task="<answer>")
   - Call wait_for_completion() again to resume waiting

2. If no input_required: proceed normally with completed results

### Timeout
If the parent does not answer within 30 seconds, the opencode MCP server
transitions the task to input_required status. If the executor doesn't
respond, the agent should make its best guess and document the assumption
in a code comment.

## gk-builder Agent

The `gk-builder` agent is a restricted opencode agent optimized for making
tests pass. It is defined in `templates/opencode.json` and deployed to the
project root at setup time.

Restrictions vs default build agent:
- No web access (websearch/webfetch disabled)
- Can ask questions (question tool enabled)
- Model: zai-coding-plan/glm-5

## Evolution-Guided Approach Selection (Step 2.5)

Between test writing (Phase 1) and implementation dispatch (Phase 2), the executor
checks for an evolution population at `.planning/evolution/{task_id}/`. This population
is built by the stop-hook across Gatekeeper loop iterations (see task 2.1).

### When Parallel Island Exploration Activates

Parallel island exploration only activates when the population has **>= 3 approaches**.
With fewer approaches, there is insufficient diversity for meaningful parallel exploration.

### Flow

1. **Check stats:**
   ```bash
   python3 scripts/evo_db.py --db-path .planning/evolution/{task_id}/ --stats
   ```
   The JSON output includes `population_size`, `num_islands`, and `per_island` breakdowns.

2. **If >= 3 approaches, sample from each island:**
   ```bash
   python3 scripts/evo_db.py --db-path .planning/evolution/{task_id}/ --sample 0
   python3 scripts/evo_db.py --db-path .planning/evolution/{task_id}/ --sample 1
   python3 scripts/evo_db.py --db-path .planning/evolution/{task_id}/ --sample 2
   ```
   Each `--sample` returns `{parent: Approach, inspirations: [Approach]}`. The
   executor uses `parent.prompt_addendum` as the approach strategy for that candidate.

3. **Spawn parallel candidates:** Each island's sampled approach becomes a separate
   opencode agent, receiving the task prompt plus `APPROACH STRATEGY: {prompt_addendum}`.

4. **Evaluate candidates:** After all complete, run `evo_eval.py --evaluate` to get
   metrics for each candidate.

5. **Store results:** All candidate metrics are stored back via `evo_db.py --add`.

6. **Select best:** The candidate with the highest `test_pass_rate` is selected.
   Its approach's `prompt_addendum` is then included in all subsequent TDD agent prompts.

### Evolution Context in TDD Agent Prompts

When a winning approach exists from Step 2.5, every TDD agent prompt includes:

```
APPROACH STRATEGY (from evolution):
{best_approach.prompt_addendum}

Make the following test pass: {test_file}

GUIDANCE:
{guidance from test dependency graph}
```

This is **additive** -- the approach strategy provides high-level direction while the
guidance provides file-level specifics. Neither replaces the other.

### Skip Conditions

- **Empty population:** No `.planning/evolution/{task_id}/` directory, or `population_size == 0`.
- **< 3 approaches:** Insufficient diversity for parallel exploration.
- **All candidates score 0.0:** Fall back to normal TDD without evolution context.

In all skip cases, the executor proceeds directly to standard Phase 2 dispatch.

## Error Handling
- If an opencode agent fails, retry once
- If retry fails, fall back to sequential implementation
- Always run full test suite after concurrent phase
