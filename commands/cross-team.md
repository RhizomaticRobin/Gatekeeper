---
description: "Execute tasks via TDD-first VGL — single-task or parallel Agent Teams"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/*:*)", "Bash(python3:*)", "Bash(cat:*)", "Bash(mkdir:*)", "Bash(rm:*)", "Read", "Task"]
---

Execute the plan orchestrator: validate the plan, find ALL unblocked tasks, check for file scope conflicts, set up per-task sessions, and launch execution.

```!
bash "${CLAUDE_PLUGIN_ROOT}/scripts/cross-team-setup.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Check the output above. Route based on the last status line:

- **CROSS_TEAM_FAILED** → follow the recovery steps below
- **CROSS_TEAM_SINGLE_OK** → proceed to single-task execution
- **CROSS_TEAM_OK** → proceed to team orchestration

---

## If CROSS_TEAM_FAILED — Diagnose and Fix

**PLAN_NOT_FOUND** — Run `/gsd-vgl:quest` first to generate a plan.
**VALIDATION_FAILED** — Fix plan.yaml errors (including must_haves) and retry.
**CROSS_TEAM_BLOCKED** — Tasks are blocked or in_progress. Wait or use `/gsd-vgl:run-away` to reset.

After fixing, run `/gsd-vgl:cross-team` again.

---

## If CROSS_TEAM_SINGLE_OK — Single-Task Execution

Only 1 unblocked task was found. Extract the task ID from the `SINGLE_TASK_ID=...` line in the setup output above, then run this command (replacing the task ID):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/single-task-setup.sh" "${CLAUDE_PLUGIN_ROOT}" "<task_id>"
```

If the last line is **CROSS_TEAM_FAILED**, follow the recovery steps above. If it is **CROSS_OK**, proceed.

**Single-task mode uses the same orchestration flow as multi-task mode** — you spawn 1 executor subagent and manage it identically. Follow the "Orchestrate the Team" section below with a single task.

---

## If CROSS_TEAM_OK — Orchestrate the Team

You are now the **Lead Orchestrator**. You do NOT write code. You coordinate worker teammates.

Read the orchestrator prompt template and follow it:

```python
prompt_template = open('${CLAUDE_PLUGIN_ROOT}/scripts/team-orchestrator-prompt.md').read()
```

### Orchestration Workflow

The per-task flow is: **Tester** (writes tests) → **Executor** (implements to pass tests) → verify.

1. **Phase 1 — Spawn tester agents** for each dispatched task:
   - One `Task(subagent_type='evogatekeeper:tester')` per task (model: opus, HAS web access)
   - Each tester gets: task prompt + session directory path
   - Testers research the domain, write comprehensive tests, confirm TDD Red, then call `assess_tests` quality gate
   - Testers return `TESTS_READY:{task_id}` or `TESTS_FAILED:{task_id}:{reason}`
   - Testers for independent tasks (same wave, no file_scope overlap) can run in parallel

2. **Phase 2 — Spawn executor agents** for each task with ready tests:
   - One `Task(subagent_type='evogatekeeper:executor')` per task (model: opus, no web access)
   - Each executor gets: task prompt + VGL instructions + session directory path
   - Executors read pre-written tests, spawn gsd-builder opencode agents concurrently, run full test suite, then call `verify_task`
   - Executors return `TASK_COMPLETE:{task_id}:{token}` or `TASK_FAILED:{task_id}:{reason}`

3. **Collect executor results** from each Task:
   - `TASK_COMPLETE:{task_id}:{token}` — validate token, mark task completed
   - `TASK_FAILED:{task_id}:{reason}` — check if failure is test-related or implementation-related

4. **Handle verify failures (test problem suspected)**:
   - If the verifier's failure details suggest test issues (impossible assertions, contradictory tests, missing coverage):
     - Re-spawn Tester: `Task(subagent_type='evogatekeeper:tester', prompt="mode=reassess ...")`
     - Include verifier failure details in the prompt
     - Collect `TESTS_READY:{task_id}` (tests fixed) or `TESTS_OK:{task_id}:...` (tests are fine)
     - If tests were fixed, re-spawn Executor
   - If failure is clearly implementation-related, re-spawn Executor directly

5. **Validate completion tokens**:
   - Read `.claude/vgl-sessions/task-{id}/verifier-token.secret` (line 1)
   - Compare with the token reported by the executor
   - Only mark complete if tokens match

6. **Mark tasks completed** via:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --complete-task {task_id} --token {token}
   ```

7. **Check for integration checkpoints** after marking a task complete:
   - If the completed task was the last task in its phase, check if that phase has `integration_check: true`
   - If so, spawn an integration-checker before dispatching next-phase tasks:
     ```
     Task(subagent_type='evogatekeeper:integration-checker',
          prompt='Verify integration between all completed phases. Check cross-phase links, data flows, type contracts, and dead endpoints. Report PASS or NEEDS_FIXES with details.')
     ```
   - If the checker reports NEEDS_FIXES with CRITICAL issues, fix them before spawning next-phase executors
   - WARNING-level issues can be noted and addressed later

8. **Check for newly unblocked tasks** after each completion:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/get-unblocked-tasks.py" .claude/plan/plan.yaml
   ```
   - For each newly unblocked task, set up its VGL session and spawn tester → executor for it

9. **When all tasks are done**:
   - All executor Tasks have returned
   - Remove `.claude/vgl-team-active`
   - Remove `.claude/vgl-sessions/`
   - Report final status

### Critical Rules

- You are the LEAD ORCHESTRATOR — never write implementation or test code
- Only YOU update plan.yaml — tester and executor sub-orchestrators must not touch it
- Always run tester BEFORE executor for each task (tester writes tests, executor implements)
- Validate every token before marking a task complete
- Testers/executors with overlapping file scopes must NOT run simultaneously
- If an executor fails 3 times, skip the task and note it for the user
- On verify failure, consider re-spawning tester in reassess mode before re-running executor
- Verify must_haves (truths, artifacts, key_links) are satisfied before marking complete
