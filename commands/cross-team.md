---
description: "Execute tasks via TDD-first Gatekeeper loop — parallel Agent Teams"
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Task", "AskUserQuestion", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__create_session", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__get_session", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__close_session", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__submit_token", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__get_next_task", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__get_token_status", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__get_pending_signals", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__mark_signal_processed", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__submit_pvg_token", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__check_phase_integration", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_evolution_attempt", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__get_evolution_context", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__encrypt_task_files", "mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__decrypt_task_file", "mcp__plugin_gatekeeper_opencode-mcp__launch_opencode", "mcp__plugin_gatekeeper_opencode-mcp__wait_for_completion", "mcp__plugin_gatekeeper_opencode-mcp__opencode_sessions"]
---

Execute the plan orchestrator: validate the plan, find ALL unblocked tasks, check for file scope conflicts, set up per-task sessions, and launch execution.

**State management**: Use the Gatekeeper MCP tools for ALL session, token, and signal operations. Do NOT manually generate tokens with `openssl rand` or write `.secret` files. The MCP server is the single source of truth for execution state.

```!
bash "${CLAUDE_PLUGIN_ROOT}/scripts/cross-team-setup.sh" "${CLAUDE_PLUGIN_ROOT}"
```

Check the output above. Route based on the last status line:

- **CROSS_TEAM_FAILED** → follow the recovery steps below
- **CROSS_TEAM_OK** → proceed to team orchestration

---

## If CROSS_TEAM_FAILED — Diagnose and Fix

**PLAN_NOT_FOUND** — Run `/gatekeeper:quest` first to generate a plan.
**VALIDATION_FAILED** — Fix plan.yaml errors (including must_haves) and retry.
**CROSS_TEAM_BLOCKED** — Tasks are blocked or in_progress. Wait or use `/gatekeeper:run-away` to reset.

After fixing, run `/gatekeeper:cross-team` again.

---

## If CROSS_TEAM_OK — Orchestrate the Team

You are now the **Lead Orchestrator**. You do NOT write code. You coordinate worker teammates.

Read the orchestrator prompt template and follow it:

```python
prompt_template = open('${CLAUDE_PLUGIN_ROOT}/scripts/team-orchestrator-prompt.md').read()
```

### Load Project Vision

Before dispatching any agents, read `.planning/PROJECT.md` and extract the vision context:

```python
project_md = open('.planning/PROJECT.md').read()
# Extract key sections for the compact PROJECT_VISION_CONTEXT block
# that gets injected into every agent prompt (see team-orchestrator-prompt.md)
```

This is mandatory. If `.planning/PROJECT.md` does not exist, run `/gatekeeper:quest` first.

If `.planning/codebase/` exists (brownfield), also read and extract summaries from STACK.md, ARCHITECTURE.md, CONVENTIONS.md, TESTING.md for the `PROJECT_CODEBASE_CONTEXT` block injected into all agent prompts.

### Encrypt Task Files (Progressive Decryption)

After loading project context, encrypt all task spec files and skeleton files for progressive access control. This ensures the orchestrator must actually complete dependency tasks before accessing downstream task specs.

```
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__encrypt_task_files(
    session_id="{session_id}",
    project_dir="{absolute path to project}",
    plan_path=".claude/plan/plan.yaml"
)
```

After encryption:
- Task-*.md files are replaced with `ENCRYPTED` placeholders
- Skeleton files are replaced with `LOCKED` placeholders
- To access a task's content, call `decrypt_task_file(session_id, task_id)` — this only succeeds after all dependency tasks have GK_COMPLETE tokens

**Before spawning any agent for a task**, decrypt it first:
```
decrypted = mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__decrypt_task_file(
    session_id="{session_id}",
    task_id="{task_id}"
)
# decrypted.task_spec contains the full task-*.md content
# decrypted.skeleton_files contains the unlocked file paths and content
```

### Session Setup — Use MCP Tools

Before dispatching any task, create a Gatekeeper session via MCP. Generate the session ID as `gk_YYYYMMDD_XXXXXX` (date + 6 hex chars).

```
mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__create_session(
    session_id="gk_{date}_{hex}",
    project_dir="{absolute path to project}",
    test_command="{test command from plan.yaml}"
)
```

Use this session_id for ALL subsequent MCP calls during this execution run.

### Orchestration Workflow

The per-phase flow is: **Phase Assessor** (defines integration contracts + format specs) → per-task: **Tester** → **Assessor** (TQG token) → **Executor** → **Verifier** (GK token) → all tasks done → **Phase Verifier** (PVG token) → next phase.

0. **Phase 0.5 — Phase assessment gate** (once per phase, before testers):
   - One `Task(subagent_type='gatekeeper:phase-assessor')` per phase (model: opus, HAS write access for specs)
   - Reads all task specs for the phase, identifies cross-task integration points
   - Creates format contracts (API shapes, data structures, wiring specs)
   - Writes per-task tester guidance files with exact interface shapes
   - Returns `PHASE_ASSESSMENT_PASS:{phase_id}:{summary}` with PAG token or `PHASE_ASSESSMENT_FAIL`
   - On PASS: record the signal and proceed:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal(
         signal_type="PHASE_ASSESSMENT_PASS",
         session_id="{session_id}",
         phase_id={phase_id},
         agent_id="phase-assessor",
         context={"summary": "{summary}"}
     )
     ```

1. **Phase 1 — Spawn tester agents** for each dispatched task:
   - One `Task(subagent_type='gatekeeper:tester')` per task (model: sonnet, HAS web access)
   - Each tester gets: task prompt + session directory path
   - Testers research the domain, write comprehensive tests, confirm TDD Red
   - Testers return `TESTS_WRITTEN:{task_id}` or `TESTS_WRITE_FAILED:{task_id}:{reason}`
   - On return, record the signal:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal(
         signal_type="TESTS_WRITTEN",  # or "TESTS_WRITE_FAILED"
         session_id="{session_id}",
         task_id="{task_id}",
         agent_id="tester"
     )
     ```
   - Testers for independent tasks (same wave, no file_scope overlap) can run in parallel

2. **Phase 1.4 — Tick check (before assessment)** for each task with ready tests:
   - One `Task(subagent_type='gatekeeper:tick-finder')` per task (model: opus, HAS write access)
   - Each tick-finder gets: task spec, file_scope.owns (test files to scan)
   - Tick-finders scan for copouts: silent failures, fallback returns, placeholders, stubs, hardcoded returns, empty implementations, obnoxiously wrong logic
   - On `TICK_CHECK_FAIL`: inject crash markers into offending files, re-spawn tester with tick list — do NOT proceed to assessment
   - On `TICK_CHECK_PASS`: proceed to assessment gate
   - Record the signal:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal(
         signal_type="TICK_CHECK_PASS",  # or "TICK_CHECK_FAIL"
         session_id="{session_id}",
         task_id="{task_id}",
         agent_id="tick-finder",
         context={"phase": "post-tester", "ticks_found": {count}}
     )
     ```

3. **Phase 1.5 — Assessment gate** for each task with ready tests:
   - One `Task(subagent_type='gatekeeper:assessor')` per task (model: opus, NO write access)
   - Each assessor gets: task spec + session directory path
   - Assessors check test possibility, comprehensiveness, quality, and must_haves alignment
   - Assessors also verify tests comply with format contracts from the phase assessor
   - Assessors return `ASSESSMENT_PASS:{tqg_token}:{summary}` or `ASSESSMENT_FAIL:{issues}`
   - On PASS: submit the TQG token via MCP:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__submit_token(
         token="{tqg_token}",
         session_id="{session_id}",
         task_id="{task_id}"
     )
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal(
         signal_type="ASSESSMENT_PASS",
         session_id="{session_id}",
         task_id="{task_id}",
         agent_id="assessor",
         context={"summary": "{summary}"}
     )
     ```
   - On FAIL: re-spawn tester with critique (max 10 rounds). Record each attempt:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_evolution_attempt(
         task_id="{task_id}",
         attempt_number={n},
         outcome="FAILURE",
         session_id="{session_id}",
         metrics={"reason": "{issues}"}
     )
     ```

4. **Phase 2 — Spawn executor agents** for each task that passed assessment:
   - One `Task(subagent_type='gatekeeper:executor')` per task (model: haiku, no web access)
   - Each executor gets: task prompt + session directory path
   - Executors read pre-written tests, implement code to make them pass, run full test suite
   - Executors return `IMPLEMENTATION_READY:{task_id}` or `TASK_FAILED:{task_id}:{reason}`
   - Record the signal:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal(
         signal_type="IMPLEMENTATION_READY",  # or "TASK_FAILED"
         session_id="{session_id}",
         task_id="{task_id}",
         agent_id="executor"
     )
     ```

5. **Phase 2.4 — Tick check (before verification)** for each task with ready implementation:
   - One `Task(subagent_type='gatekeeper:tick-finder')` per task (model: opus, HAS write access)
   - Each tick-finder gets: task spec, file_scope.owns (implementation files to scan)
   - Tick-finders scan for copouts the executor snuck in: silent failures, fallback returns, hardcoded magic numbers matching test fixtures, copy-pasted test values, stubs, empty implementations
   - On `TICK_CHECK_FAIL`: inject crash markers into offending files, re-spawn executor with tick list — do NOT proceed to verifier
   - On `TICK_CHECK_PASS`: proceed to verification gate
   - Record the signal:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal(
         signal_type="TICK_CHECK_PASS",  # or "TICK_CHECK_FAIL"
         session_id="{session_id}",
         task_id="{task_id}",
         agent_id="tick-finder",
         context={"phase": "post-executor", "ticks_found": {count}}
     )
     ```

6. **Phase 2.5 — Verification gate** for each task with ready implementation:
   - One `Task(subagent_type='gatekeeper:verifier')` per task (model: opus, NO write access)
   - Each verifier gets: task spec + test command + session directory path + `dev_server_url` (MANDATORY)
   - **The `dev_server_url` MUST be provided to every verifier.** Visual verification via Playwright is required for ALL tasks, including backend/CLI tasks. The plan must define a `dev_server_command` and each task must have a `playwright_url`.
   - Verifiers perform deep code inspection, run tests independently, check must_haves, AND run Playwright visual verification
   - Verifiers return `VERIFICATION_PASS`, `VERIFICATION_FAIL:{critique}`, or `VERIFICATION_PAUSED:playwright_unavailable`
   - On PASS: submit the GK completion token via MCP and mark task completed:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__submit_token(
         token="GK_COMPLETE_{32 hex chars}",
         session_id="{session_id}",
         task_id="{task_id}"
     )
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal(
         signal_type="VERIFICATION_PASS",
         session_id="{session_id}",
         task_id="{task_id}",
         agent_id="verifier"
     )
     python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --complete-task {task_id} --token {gk_token}
     ```
   - On `VERIFICATION_PAUSED:playwright_unavailable`: **STOP all execution.** Use AskUserQuestion to alert the user that Playwright is unavailable and request intervention. Do NOT proceed, do NOT skip visual verification, do NOT mark any tasks complete. Resume only after user confirms Playwright is working.
   - On FAIL (test issue): re-spawn tester in reassess mode, then assessor + executor + verifier
   - On FAIL (impl issue): re-spawn executor with critique (max 10 rounds)
   - Record each failure attempt:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_evolution_attempt(
         task_id="{task_id}",
         attempt_number={n},
         outcome="FAILURE",
         session_id="{session_id}",
         metrics={"critique": "{critique}", "failure_type": "test_issue|impl_issue"}
     )
     ```

7. **Handle verify failures (test problem suspected)**:
   - If the verifier's failure details suggest test issues:
     - Re-spawn Tester: `Task(subagent_type='gatekeeper:tester', prompt="mode=reassess ...")`
     - Include verifier failure details in the prompt
     - Collect `TESTS_WRITTEN:{task_id}` (tests fixed) or `TESTS_OK:{task_id}:...` (tests are fine)
     - If tests were fixed, re-run assessor → executor → verifier
   - If failure is clearly implementation-related, re-spawn executor directly with verifier critique
   - Check evolution context for patterns across attempts:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__get_evolution_context(
         task_id="{task_id}"
     )
     ```

8. **Mark tasks completed** — use MCP for token submission, plan_utils for plan.yaml update:
   ```
   # Generate token hex (32 chars)
   token_hex = random 32 hex chars
   gk_token = "GK_COMPLETE_{token_hex}"

   # Submit via MCP (source of truth for execution state)
   mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__submit_token(
       token=gk_token,
       session_id="{session_id}",
       task_id="{task_id}"
   )

   # Update plan.yaml (source of truth for plan state)
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --complete-task {task_id} --token {gk_token}
   ```

9. **Phase verification gate** after marking a task complete:
   - If the completed task was the last task in its phase AND the phase has `integration_check: true`:
   - First, check phase integration artifacts via MCP:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__check_phase_integration(
         phase_id={phase_id},
         required_artifacts=["{list of artifact paths from phase must_haves}"],
         project_dir="{project_dir}"
     )
     ```
   - Spawn a phase-verifier (model: opus, read-only) to verify integration contracts and cross-phase wiring:
     ```
     Task(subagent_type='gatekeeper:phase-verifier', model='opus',
          prompt='phase_id: {id}, integration_specs_dir: .claude/plan/phases/phase-{id}/integration-specs/, ...')
     ```
   - On `PHASE_VERIFICATION_PASS:{phase_id}`: submit PVG token via MCP:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__submit_pvg_token(
         session_id="{session_id}",
         token_value="PVG_COMPLETE_{32 hex chars}",
         phase_id={phase_id},
         integration_check_passed=true
     )
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal(
         signal_type="PHASE_VERIFICATION_PASS",
         session_id="{session_id}",
         phase_id={phase_id},
         agent_id="phase-verifier"
     )
     ```
   - On `PHASE_VERIFICATION_FAIL` with CRITICAL issues: fix before next phase
   - WARNING-level issues can be noted and addressed later
   - Next phase starts with Phase 0.5 (phase assessor) before testers

10. **Check for newly unblocked tasks** after each completion:
   ```
   # Use MCP for next task suggestion
   mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__get_next_task(
       session_id="{session_id}"
   )

   # Cross-reference with plan.yaml for full task details
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/get-unblocked-tasks.py" .claude/plan/plan.yaml
   ```
   - For each newly unblocked task, spawn tester → tick-check → assessor → executor → tick-check → verifier

11. **When all tasks are done**:
   - All verifier Tasks have returned PASS
   - Verify all tokens submitted via MCP:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__get_token_status(
         session_id="{session_id}"
     )
     ```
   - Close the session:
     ```
     mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__close_session(
         session_id="{session_id}"
     )
     ```
   - Remove `.claude/gk-team-active`
   - Remove `.claude/gk-sessions/`
   - Remove `.claude/plan-locked`
   - Report final status

12. **Hyperphase N — Evolutionary Optimization (optional)**:
   - Steps 1–11 above are **Hyperphase 1** (the main Gatekeeper Pipeline)
   - After all Hyperphase 1 tasks are completed, check if `plan.yaml metadata.hyperphase: true`
   - If enabled, follow Section 8 of the team-orchestrator-prompt (scout → optimize → verify)
   - This is opt-in per project and can also be run standalone via `/gatekeeper:hyperphase`

### Critical Rules

- You are the LEAD ORCHESTRATOR — never write implementation or test code
- Only YOU update plan.yaml — tester, assessor, executor, and verifier sub-agents must not touch it
- **Use MCP tools for ALL token submission and signal recording** — do NOT manually generate tokens with `openssl rand` or write `.secret` files
- Always run tester → tick-check → assessor → executor → tick-check → verifier for each task
- Testers/executors with overlapping file scopes must NOT run simultaneously
- If an executor fails 3 times, skip the task and note it for the user
- On verify failure, check category (test_issue vs impl_issue) to decide which agent to re-spawn
- Verify must_haves (truths, artifacts, key_links) are satisfied before marking complete
- The orchestrator generates GK/PAG/PVG tokens; the assessor generates TQG tokens in its output signal
- Token chain per task: PAG (phase start) → TQG (test quality) → GK (task verification) → PVG (phase end)
- All tokens must be submitted via `mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__submit_token` or `submit_pvg_token`
- All agent signals must be recorded via `mcp__plugin_gatekeeper_gatekeeper-evolve-mcp__record_agent_signal`
- **Playwright visual verification is MANDATORY for every task** — always pass `dev_server_url` to verifiers. If a verifier returns `VERIFICATION_PAUSED:playwright_unavailable`, STOP all execution and ask the user for help via AskUserQuestion. Do NOT skip visual verification.
- Every task must have a `tests.qualitative.playwright_url` — if missing, the plan is incomplete
