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

**PLAN_NOT_FOUND** — Run `/gatekeeper:quest` first to generate a plan.
**VALIDATION_FAILED** — Fix plan.yaml errors (including must_haves) and retry.
**CROSS_TEAM_BLOCKED** — Tasks are blocked or in_progress. Wait or use `/gatekeeper:run-away` to reset.

After fixing, run `/gatekeeper:cross-team` again.

---

## If CROSS_TEAM_SINGLE_OK — Single-Task Execution

Only 1 unblocked task was found. Extract the task ID from the `SINGLE_TASK_ID=...` line in the setup output above, then run this command (replacing the task ID):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/single-task-setup.sh" "${CLAUDE_PLUGIN_ROOT}" "<task_id>"
```

If the last line is **CROSS_TEAM_FAILED**, follow the recovery steps above. If it is **CROSS_OK**, proceed.

**Single-task mode uses the same orchestration flow as multi-task mode** — you spawn 1 tester + assessor + executor + verifier subagent and manage it identically. Follow the "Orchestrate the Team" section below with a single task.

---

## If CROSS_TEAM_OK — Orchestrate the Team

You are now the **Lead Orchestrator**. You do NOT write code. You coordinate worker teammates.

Read the orchestrator prompt template and follow it:

```python
prompt_template = open('${CLAUDE_PLUGIN_ROOT}/scripts/team-orchestrator-prompt.md').read()
```

### Orchestration Workflow

The per-task flow is: **Tester** (writes tests) → **Assessor** (evaluates quality) → **Executor** (implements to pass tests) → **Verifier** (inspects independently) → complete.

1. **Phase 1 — Spawn tester agents** for each dispatched task:
   - One `Task(subagent_type='gatekeeper:tester')` per task (model: sonnet, HAS web access)
   - Each tester gets: task prompt + session directory path
   - Testers research the domain, write comprehensive tests, confirm TDD Red
   - Testers return `TESTS_WRITTEN:{task_id}` or `TESTS_WRITE_FAILED:{task_id}:{reason}`
   - Testers for independent tasks (same wave, no file_scope overlap) can run in parallel

2. **Phase 1.5 — Assessment gate** for each task with ready tests:
   - One `Task(subagent_type='gatekeeper:assessor')` per task (model: opus, NO write access)
   - Each assessor gets: task spec + session directory path
   - Assessors check test possibility, comprehensiveness, quality, and must_haves alignment
   - Assessors return `ASSESSMENT_PASS:{summary}` or `ASSESSMENT_FAIL:{issues}`
   - On FAIL: re-spawn tester with critique (max 3 rounds)

3. **Phase 2 — Spawn executor agents** for each task that passed assessment:
   - One `Task(subagent_type='gatekeeper:executor')` per task (model: haiku, no web access)
   - Each executor gets: task prompt + session directory path
   - Executors read pre-written tests, spawn gsd-builder opencode agents concurrently, run full test suite
   - Executors return `IMPLEMENTATION_READY:{task_id}` or `TASK_FAILED:{task_id}:{reason}`

4. **Phase 2.5 — Verification gate** for each task with ready implementation:
   - One `Task(subagent_type='gatekeeper:verifier')` per task (model: opus, NO write access)
   - Each verifier gets: task spec + test command + session directory path
   - Verifiers perform deep code inspection, run tests independently, check must_haves
   - Verifiers return `VERIFICATION_PASS` or `VERIFICATION_FAIL:{critique}`
   - On PASS: orchestrator generates token, marks task completed
   - On FAIL (test issue): re-spawn tester in reassess mode, then assessor + executor + verifier
   - On FAIL (impl issue): re-spawn executor with critique (max 3 rounds)

5. **Handle verify failures (test problem suspected)**:
   - If the verifier's failure details suggest test issues:
     - Re-spawn Tester: `Task(subagent_type='gatekeeper:tester', prompt="mode=reassess ...")`
     - Include verifier failure details in the prompt
     - Collect `TESTS_WRITTEN:{task_id}` (tests fixed) or `TESTS_OK:{task_id}:...` (tests are fine)
     - If tests were fixed, re-run assessor → executor → verifier
   - If failure is clearly implementation-related, re-spawn executor directly with verifier critique

6. **Mark tasks completed** via:
   ```bash
   token=$(openssl rand -hex 32 | head -c 32)
   vgl_token="VGL_COMPLETE_${token}"
   # Write token to verifier-token.secret (line 1, preserve TEST_CMD lines)
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --complete-task {task_id} --token {vgl_token}
   ```

7. **Check for integration checkpoints** after marking a task complete:
   - If the completed task was the last task in its phase, check if that phase has `integration_check: true`
   - If so, spawn an integration-checker before dispatching next-phase tasks:
     ```
     Task(subagent_type='gatekeeper:integration-checker',
          prompt='Verify integration between all completed phases. Check cross-phase links, data flows, type contracts, and dead endpoints. Report PASS or NEEDS_FIXES with details.')
     ```
   - If the checker reports NEEDS_FIXES with CRITICAL issues, fix them before spawning next-phase executors
   - WARNING-level issues can be noted and addressed later

8. **Check for newly unblocked tasks** after each completion:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/get-unblocked-tasks.py" .claude/plan/plan.yaml
   ```
   - For each newly unblocked task, set up its VGL session and spawn tester → assessor → executor → verifier

9. **When all tasks are done**:
   - All verifier Tasks have returned PASS
   - Remove `.claude/vgl-team-active`
   - Remove `.claude/vgl-sessions/`
   - Remove `.claude/plan-locked`
   - Report final status

10. **Phase 5 — Superphase (optional)**:
   - After all tasks are completed, check if `plan.yaml metadata.superphase: true`
   - If enabled, follow Section 8 of the team-orchestrator-prompt (scout → optimize → verify)
   - This is opt-in per project and can also be run standalone via `/gatekeeper:superphase`

### Critical Rules

- You are the LEAD ORCHESTRATOR — never write implementation or test code
- Only YOU update plan.yaml — tester, assessor, executor, and verifier sub-agents must not touch it
- Always run tester → assessor → executor → verifier for each task
- Testers/executors with overlapping file scopes must NOT run simultaneously
- If an executor fails 3 times, skip the task and note it for the user
- On verify failure, check category (test_issue vs impl_issue) to decide which agent to re-spawn
- Verify must_haves (truths, artifacts, key_links) are satisfied before marking complete
- The orchestrator generates and writes cryptographic tokens — no agent handles tokens
