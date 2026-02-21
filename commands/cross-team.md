---
description: "Execute tasks via TDD-first Gatekeeper loop — single-task or parallel Agent Teams"
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

The per-phase flow is: **Phase Assessor** (defines integration contracts + format specs) → per-task: **Tester** → **Assessor** (TQG token) → **Executor** → **Verifier** (GK token) → all tasks done → **Phase Verifier** (PVG token) → next phase.

0. **Phase 0.5 — Phase assessment gate** (once per phase, before testers):
   - One `Task(subagent_type='gatekeeper:phase-assessor')` per phase (model: opus, HAS write access for specs)
   - Reads all task specs for the phase, identifies cross-task integration points
   - Creates format contracts (API shapes, data structures, wiring specs)
   - Writes per-task tester guidance files with exact interface shapes
   - Returns `PHASE_ASSESSMENT_PASS:{phase_id}:{summary}` with PAG token or `PHASE_ASSESSMENT_FAIL`
   - On PASS: orchestrator generates `PAG_COMPLETE_{hex}` token, proceeds to spawn testers with format guidance injected

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
   - Assessors also verify tests comply with format contracts from the phase assessor
   - Assessors return `ASSESSMENT_PASS:{tqg_token}:{summary}` or `ASSESSMENT_FAIL:{issues}`
   - On PASS: orchestrator extracts TQG token, writes to `assessor-token.secret`
   - On FAIL: re-spawn tester with critique (max 3 rounds)

3. **Phase 2 — Spawn executor agents** for each task that passed assessment:
   - One `Task(subagent_type='gatekeeper:executor')` per task (model: haiku, no web access)
   - Each executor gets: task prompt + session directory path
   - Executors read pre-written tests, spawn Task subagents concurrently, run full test suite
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
   gk_token="GK_COMPLETE_${token}"
   # Write token to verifier-token.secret (line 1, preserve TEST_CMD lines)
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --complete-task {task_id} --token {gk_token}
   ```

7. **Phase verification gate** after marking a task complete:
   - If the completed task was the last task in its phase AND the phase has `integration_check: true`:
   - Spawn a phase-verifier (model: opus, read-only) to verify integration contracts and cross-phase wiring:
     ```
     Task(subagent_type='gatekeeper:phase-verifier', model='opus',
          prompt='phase_id: {id}, integration_specs_dir: .claude/plan/phases/phase-{id}/integration-specs/, ...')
     ```
   - On `PHASE_VERIFICATION_PASS:{phase_id}`: orchestrator generates `PVG_COMPLETE_{hex}` token, writes to `phase-verifier-token.secret`
   - On `PHASE_VERIFICATION_FAIL` with CRITICAL issues: fix before next phase
   - WARNING-level issues can be noted and addressed later
   - Next phase starts with Phase 0.5 (phase assessor) before testers

8. **Check for newly unblocked tasks** after each completion:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/get-unblocked-tasks.py" .claude/plan/plan.yaml
   ```
   - For each newly unblocked task, set up its Gatekeeper session and spawn tester → assessor → executor → verifier

9. **When all tasks are done**:
   - All verifier Tasks have returned PASS
   - Remove `.claude/gk-team-active`
   - Remove `.claude/gk-sessions/`
   - Remove `.claude/plan-locked`
   - Report final status

10. **Hyperphase N — Evolutionary Optimization (optional)**:
   - Steps 1–9 above are **Hyperphase 1** (the main Gatekeeper Pipeline)
   - After all Hyperphase 1 tasks are completed, check if `plan.yaml metadata.hyperphase: true`
   - If enabled, follow Section 8 of the team-orchestrator-prompt (scout → optimize → verify)
   - This is opt-in per project and can also be run standalone via `/gatekeeper:hyperphase`

### Critical Rules

- You are the LEAD ORCHESTRATOR — never write implementation or test code
- Only YOU update plan.yaml — tester, assessor, executor, and verifier sub-agents must not touch it
- Always run tester → assessor → executor → verifier for each task
- Testers/executors with overlapping file scopes must NOT run simultaneously
- If an executor fails 3 times, skip the task and note it for the user
- On verify failure, check category (test_issue vs impl_issue) to decide which agent to re-spawn
- Verify must_haves (truths, artifacts, key_links) are satisfied before marking complete
- The orchestrator generates GK/PAG/PVG tokens; the assessor generates TQG tokens in its output signal
- Token chain per task: PAG (phase start) → TQG (test quality) → GK (task verification) → PVG (phase end)
