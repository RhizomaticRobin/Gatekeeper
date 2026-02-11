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

## If CROSS_TEAM_SINGLE_OK — Single-Task VGL Execution

Only 1 unblocked task was found. Extract the task ID from the setup output (the `SINGLE_TASK_ID=...` line) and run the single-task setup script.

**IMPORTANT:** Replace `__TASK_ID__` below with the actual task ID from the `SINGLE_TASK_ID=...` line in the setup output above.

```!
bash "${CLAUDE_PLUGIN_ROOT}/scripts/single-task-setup.sh" "${CLAUDE_PLUGIN_ROOT}" "__TASK_ID__"
```

If the last line is **CROSS_TEAM_FAILED**, follow the recovery steps above. If it is **CROSS_OK**, proceed to the single-task workflow below.

### Single-Task Workflow (TDD-First + Opencode Concurrency)

This is a **Plan-Mode Verifier-Gated Loop** with TDD-first execution and opencode MCP concurrent agents. Each task is verified with BOTH quantitative tests AND qualitative Playwright visual verification.

Follow this workflow strictly in order:

#### Step 1: Read the Task Prompt and must_haves
Read the task prompt carefully. Identify:
- Backend deliverables (API routes, models, logic)
- Frontend deliverables (components, pages, interactions)
- must_haves: truths (invariants), artifacts (files that must exist), key_links (references)

#### Step 2: Write ALL Tests First (Red Phase — TDD)
Before writing ANY implementation code:
- Create test files for every deliverable
- Write unit tests covering the contract, edge cases, error conditions
- Write integration tests covering API endpoints
- Write tests that validate must_haves truths are enforced
- Tests MUST fail at this point (Red phase) — that is correct

#### Step 3: Dispatch Opencode Agents (1 Test Per Agent)
Read the **Test Dependency Graph** from the task prompt. Dispatch in waves:
- Wave 1: launch fresh agents for all tests with no dependencies (concurrent)
- Wave 2+: for dependent tests, **continue the session** of the agent that completed the dependency — it already has context about its implementation
- If a test has multiple dependencies, continue the most significant dependency's agent and tell it to review the other dependencies' work first
- Each agent gets exactly 1 test file + the guidance from the graph

#### Step 4: Wait for Completion (Per Wave)
Use `wait_for_completion` after each wave. Track `test → sessionId` for continuations.
- Review each agent's output for errors or incomplete work
- If any agent failed, address its issues before dispatching next wave
- If any agent has status "input_required", answer via `launch_opencode(sessionId=<id>, task="<answer>")`, then call `wait_for_completion()` again
- Verify the wave's tests pass before dispatching the next wave

#### Step 5: Run Full Test Suite (Green Phase)
Run the quantitative test command yourself:
- Verify ALL tests pass
- If any fail, fix the issues and re-run
- Do NOT proceed until the full suite is green

#### Step 6: Spawn the Verifier Subagent
When all tests pass and implementation is complete:
```
Task(subagent_type='general-purpose', model='opus',
     prompt=open('.claude/verifier-prompt.local.md').read())
```

The Verifier will:
- Run quantitative tests independently
- Perform Playwright visual verification of qualitative criteria
- Navigate to pages, interact with UI, take screenshots
- Choose its own test inputs (non-deterministic)
- Validate must_haves truths hold and artifacts exist
- Only grant the completion token if ALL checks pass

On completion, the plan will automatically transition to the next task.

#### Critical Rules (Single-Task)
- You CANNOT complete the loop directly — the Verifier must approve
- The Verifier uses Playwright to visually verify the UI works
- Trust the process and iterate until the Verifier approves
- Do NOT modify plan.yaml or any .claude/ state files
- Do NOT set task status yourself — only the Verifier and system scripts control task lifecycle
- Follow TDD order: tests FIRST, then implementation, then verification
- Use opencode concurrency for implementation — do not implement serially what can be done in parallel

---

## If CROSS_TEAM_OK — Orchestrate the Team

You are now the **Lead Orchestrator**. You do NOT write code. You coordinate worker teammates.

Read the orchestrator prompt template and follow it:

```python
prompt_template = open('${CLAUDE_PLUGIN_ROOT}/scripts/team-orchestrator-prompt.md').read()
```

### Orchestration Workflow

1. **Spawn executor sub-orchestrators** for each dispatched task:
   - One `Task(subagent_type='executor')` per task (model: opus, no web access)
   - Each executor gets: task prompt + VGL instructions + TDD-first workflow + session directory path
   - Executors write ALL tests first, spawn gsd-builder opencode agents concurrently, wait for completion, run full test suite, then spawn their own Verifier subagents
   - Executors return completion tokens or failure reasons in their Task output

2. **Collect executor results** from each Task:
   - `TASK_COMPLETE:{task_id}:{token}` — validate token, mark task completed
   - `TASK_FAILED:{task_id}:{reason}` — log failure, decide retry or skip

3. **Validate completion tokens**:
   - Read `.claude/vgl-sessions/task-{id}/verifier-token.secret` (line 1)
   - Compare with the token reported by the executor
   - Only mark complete if tokens match

4. **Mark tasks completed** via:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --complete-task {task_id}
   ```

5. **Check for integration checkpoints** after marking a task complete:
   - If the completed task was the last task in its phase, check if that phase has `integration_check: true`
   - If so, spawn an integration-checker before dispatching next-phase tasks:
     ```
     Task(subagent_type='integration-checker',
          prompt='Verify integration between all completed phases. Check cross-phase links, data flows, type contracts, and dead endpoints. Report PASS or NEEDS_FIXES with details.')
     ```
   - If the checker reports NEEDS_FIXES with CRITICAL issues, fix them before spawning next-phase executors
   - WARNING-level issues can be noted and addressed later

6. **Check for newly unblocked tasks** after each completion:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/get-unblocked-tasks.py" .claude/plan/plan.yaml
   ```
   - For each newly unblocked task, set up its VGL session and spawn a new executor sub-orchestrator

7. **When all tasks are done**:
   - All executor Tasks have returned
   - Remove `.claude/vgl-team-active`
   - Remove `.claude/vgl-sessions/`
   - Report final status

### Critical Rules

- You are the LEAD ORCHESTRATOR — never write implementation code
- Only YOU update plan.yaml — executor sub-orchestrators must not touch it
- Validate every token before marking a task complete
- Executors with overlapping file scopes must NOT run simultaneously
- If an executor fails 3 times, skip the task and note it for the user
- Executors are sub-orchestrators: they spawn gsd-builder opencode agents, not implement directly
- Verify must_haves (truths, artifacts, key_links) are satisfied before marking complete
