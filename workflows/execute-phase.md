<purpose>
Execute all tasks in a phase using wave-based parallel execution. Orchestrator stays lean by delegating task execution to subagents. Tasks in the same wave with non-overlapping file_scope can run in parallel.
</purpose>

<core_principle>
The orchestrator's job is coordination, not execution. Each subagent loads the full execute-task context itself. Orchestrator discovers tasks from plan.yaml, analyzes wave grouping and file_scope overlap, spawns agents, handles checkpoints, collects results.
</core_principle>

<required_reading>
Read plan.yaml before any operation to load project context and task definitions.
Read config if available for execution behavior settings.
</required_reading>

<process>

<step name="resolve_model_profile" priority="first">
Read model profile for agent spawning:

```bash
MODEL_PROFILE=$(cat plan.yaml 2>/dev/null | grep -o 'model_profile:[[:space:]]*[^[:space:]]*' | cut -d: -f2 | tr -d ' "' || echo "balanced")
```

Default to "balanced" if not set.

**Model lookup table:**

| Agent | quality | balanced | budget |
|-------|---------|----------|--------|
| executor | opus | sonnet | sonnet |
| verifier | sonnet | sonnet | haiku |
| integration-checker | sonnet | sonnet | haiku |

Store resolved models for use in Task calls below.
</step>

<step name="load_project_state">
Before any operation, read project state from plan.yaml:

```bash
cat plan.yaml 2>/dev/null
```

**If file exists:** Parse and internalize:
- Current milestone and phase
- Task inventory with wave assignments, file_scope, and dependencies
- Accumulated decisions (constraints on this execution)
- Blockers/concerns (things to watch for)

**If plan.yaml missing but project artifacts exist:**
```
plan.yaml missing but project artifacts exist.
Options:
1. Reconstruct from existing artifacts
2. Continue without project state (may lose accumulated context)
```

**If no project artifacts exist:** Error - project not initialized.
</step>

<step name="validate_phase">
Confirm phase exists and has tasks in plan.yaml:

```bash
# Extract tasks for the given phase from plan.yaml
TASKS=$(grep -A 100 "phase: ${PHASE_ARG}" plan.yaml 2>/dev/null | grep "id:" || true)
TASK_COUNT=$(echo "$TASKS" | grep -c "id:" 2>/dev/null || echo 0)
if [ "$TASK_COUNT" -eq 0 ]; then
  echo "ERROR: No tasks found for phase '${PHASE_ARG}' in plan.yaml"
  exit 1
fi
```

Report: "Found {N} tasks in phase {phase}"
</step>

<step name="discover_tasks">
List all tasks for the phase and extract metadata from plan.yaml:

For each task, extract:
- `id` - Task identifier (e.g., "1.1")
- `wave: N` - Execution wave (pre-computed in plan.yaml)
- `file_scope: [...]` - Files this task touches
- `autonomous: true/false` - Whether task has checkpoints
- `status` - Current completion status

Build task inventory:
- Task file path (task-{id}.md)
- Task ID
- Wave number
- File scope list
- Autonomous flag
- Completion status

**Filtering:**
- Skip completed tasks (status: done)
- If `--gaps-only` flag: also skip tasks where `gap_closure` is not `true`

If all tasks filtered out, report "No matching incomplete tasks" and exit.
</step>

<step name="group_by_wave">
Read `wave` from each task in plan.yaml and group by wave number:

**Group tasks:**
```
waves = {
  1: [1.1, 1.2],
  2: [2.1, 2.2],
  3: [3.1]
}
```

**No dependency analysis needed.** Wave numbers are pre-computed during planning.

**Parallel eligibility within a wave:**
Tasks in the same wave can run in parallel if their `file_scope` arrays do not overlap. If file_scope overlaps, those tasks must run sequentially within the wave.

```
Wave 1:
  1.1 (file_scope: [src/auth.ts, src/login.tsx])  -- parallel group A
  1.2 (file_scope: [src/api/users.ts])             -- parallel group A (no overlap)
  1.3 (file_scope: [src/auth.ts, src/session.ts])  -- sequential after 1.1 (overlaps auth.ts)
```

Report wave structure with context:
```
## Execution Plan

**Phase {X}: {Name}** -- {total_tasks} tasks across {wave_count} waves

| Wave | Tasks | Parallel? | What it builds |
|------|-------|-----------|----------------|
| 1 | 1.1, 1.2 | Yes (no file_scope overlap) | {from task objectives} |
| 1 | 1.3 | After 1.1 (overlaps auth.ts) | {from task objectives} |
| 2 | 2.1 | Solo | {from task objectives} |

```

The "What it builds" column comes from skimming task names/objectives. Keep it brief (3-8 words).
</step>

<step name="execute_waves">
Execute each wave in sequence. Tasks within a wave with non-overlapping file_scope run in parallel.

**For each wave:**

1. **Describe what's being built (BEFORE spawning):**

   Read each task's objective from task-{id}.md. Extract what's being built and why it matters.

   **Output:**
   ```
   ---

   ## Wave {N}

   **task-{id}: {Task Name}**
   {2-3 sentences: what this builds, key technical approach, why it matters in context}

   **task-{id}: {Task Name}** (if parallel)
   {same format}

   Spawning {count} agent(s)...

   ---
   ```

   **Examples:**
   - Bad: "Executing authentication task"
   - Good: "OAuth2 integration with PKCE flow -- implements token exchange, refresh logic, and secure storage. Required before any authenticated API calls can proceed."

2. **Spawn all parallel-eligible agents in wave simultaneously:**

   Before spawning, read file contents. The `@` syntax does not work across Task() boundaries - content must be inlined.

   ```bash
   # Read each task file in the wave
   TASK_CONTENT=$(cat "task-{id}.md")
   PLAN_CONTENT=$(cat plan.yaml)
   ```

   Use Task tool with multiple parallel calls for non-overlapping file_scope tasks. Each agent gets prompt with inlined content:

   ```
   <objective>
   Execute task-{id} of phase {phase_name}.

   Commit each sub-step atomically. Report completion via checkpoint format.
   </objective>

   <execution_context>
   Use /cross-team command for cross-cutting concerns.
   </execution_context>

   <context>
   Task:
   {task_content}

   Project plan:
   {plan_content}
   </context>

   <success_criteria>
   - [ ] All sub-steps executed
   - [ ] Each sub-step committed individually
   - [ ] checkpoint(task-{id}): {summary} reported on completion
   - [ ] plan.yaml task status updated
   </success_criteria>
   ```

3. **Wait for all agents in wave to complete:**

   Task tool blocks until each agent finishes. All parallel agents return together.

4. **Report completion and what was built:**

   For each completed agent:
   - Verify checkpoint(task-{id}) was reported
   - Extract what was built from checkpoint summary
   - Note any issues or deviations

   **Output:**
   ```
   ---

   ## Wave {N} Complete

   **task-{id}: {Task Name}**
   {What was built -- from checkpoint summary}
   {Notable deviations or discoveries, if any}

   **task-{id}: {Task Name}** (if parallel)
   {same format}

   {If more waves: brief note on what this enables for next wave}

   ---
   ```

   **Examples:**
   - Bad: "Wave 2 complete. Proceeding to Wave 3."
   - Good: "Auth system complete -- OAuth2 PKCE flow, token refresh, secure storage. API integration (Wave 3) can now use authenticated requests."

5. **Handle failures:**

   If any agent in wave fails:
   - Report which task failed and why
   - Ask user: "Continue with remaining waves?" or "Stop execution?"
   - If continue: proceed to next wave (dependent tasks may also fail)
   - If stop: exit with partial completion report

6. **Execute checkpoint tasks between waves:**

   See `<checkpoint_handling>` for details.

7. **Proceed to next wave**

</step>

<step name="checkpoint_handling">
Tasks with `autonomous: false` require user interaction.

**Detection:** Check `autonomous` field in plan.yaml task definition.

**Execution flow for checkpoint tasks:**

1. **Spawn agent for checkpoint task:**
   ```
   Task(prompt="{subagent-task-prompt}", subagent_type="gatekeeper:executor", model="{executor_model}")
   ```

2. **Agent runs until checkpoint:**
   - Executes auto steps normally
   - Reaches checkpoint step (e.g., `type="checkpoint:human-verify"`) or auth gate
   - Agent returns with structured checkpoint

3. **Agent return includes (structured format):**
   - Completed steps table with commit hashes and files
   - Current step name and blocker
   - Checkpoint type and details for user
   - What's awaited from user

4. **Orchestrator presents checkpoint to user:**

   Extract and display the "Checkpoint Details" and "Awaiting" sections from agent return:
   ```
   ## Checkpoint: [Type]

   **Task:** task-{id}: {Task Name}
   **Progress:** 2/3 steps complete

   [Checkpoint Details section from agent return]

   [Awaiting section from agent return]
   ```

5. **User responds:**
   - "approved" / "done" -> spawn continuation agent
   - Description of issues -> spawn continuation agent with feedback
   - Decision selection -> spawn continuation agent with choice

6. **Spawn continuation agent (NOT resume):**

   ```
   Task(
     prompt=filled_continuation_template,
     subagent_type="gatekeeper:executor",
     model="{executor_model}"
   )
   ```

   Fill template with:
   - `{completed_steps_table}`: From agent's checkpoint return
   - `{resume_step_number}`: Current step from checkpoint
   - `{resume_step_name}`: Current step name from checkpoint
   - `{user_response}`: What user provided
   - `{resume_instructions}`: Based on checkpoint type

7. **Continuation agent executes:**
   - Verifies previous commits exist
   - Continues from resume point
   - May hit another checkpoint (repeat from step 4)
   - Or completes task

8. **Repeat until task completes or user stops**

**Checkpoint format:** All agents report completion using:
```
checkpoint(task-{id}): {summary of what was accomplished}
```

**Why fresh agent instead of resume:**
Resume relies on Claude Code's internal serialization which breaks with parallel tool calls.
Fresh agents with explicit state are more reliable and maintain full context.

**Checkpoint in parallel context:**
If a task in a parallel wave has a checkpoint:
- Spawn as normal
- Agent pauses at checkpoint and returns with structured state
- Other parallel agents may complete while waiting
- Present checkpoint to user
- Spawn continuation agent with user response
- Wait for all agents to finish before next wave
</step>

<step name="aggregate_results">
After all waves complete, aggregate results:

```markdown
## Phase {X}: {Name} Execution Complete

**Waves executed:** {N}
**Tasks completed:** {M} of {total}

### Wave Summary

| Wave | Tasks | Status |
|------|-------|--------|
| 1 | 1.1, 1.2 | Complete |
| CP | 1.3 | Verified |
| 2 | 2.1 | Complete |
| 3 | 3.1 | Complete |

### Task Details

1. **1.1**: [one-liner from checkpoint summary]
2. **1.2**: [one-liner from checkpoint summary]
...

### Issues Encountered
[Aggregate from all checkpoints, or "None"]
```
</step>

<step name="verify_phase_goal">
Verify phase achieved its GOAL, not just completed its TASKS.

**Spawn verifier via MCP:**

For phase-level verification, use the `verify_task` MCP tool with the phase's representative task ID (typically the last task in the phase):

```
verify_task(task_id="{last_task_id_in_phase}")
```

The verifier MCP server handles everything internally — loading the verifier prompt, spawning a locked-down Claude Code agent, running tests, and performing Playwright visual verification.
```

**Read verification status and route:**

| Status | Action |
|--------|--------|
| `passed` | Continue to update_plan |
| `human_needed` | Present items to user, get approval or feedback |
| `gaps_found` | Present gap summary, offer `/verify-milestone` for deeper check |

**If passed:**

Phase goal verified. Proceed to update_plan.

**If human_needed:**

```markdown
## Phase {X}: {Name} -- Human Verification Required

All automated checks passed. {N} items need human testing:

### Human Verification Checklist

{Extract from verification report human_verification section}

---

**After testing:**
- "approved" -> continue to update_plan
- Report issues -> will route to gap closure planning
```

If user approves -> continue to update_plan.
If user reports issues -> treat as gaps_found.

**If gaps_found:**

Present gaps and offer next command:

```markdown
## Phase {X}: {Name} -- Gaps Found

**Score:** {N}/{M} must-haves verified
**Report:** see verification output

### What's Missing

{Extract gap summaries from verification gaps section}

---

## Next Up

**Plan gap closure** -- create additional tasks to complete the phase

`/verify-milestone`

---

**Also available:**
- Review verification report for full details
- `/cross-team` -- coordinate cross-cutting fixes or parallel execution
```
</step>

<step name="update_plan">
Update plan.yaml to reflect phase completion:

- Mark phase status as complete
- Update completion timestamps
- Update task statuses

Commit phase completion:
```bash
git add plan.yaml
git commit -m "docs(phase-{X}): complete phase execution"
```
</step>

<step name="offer_next">
Present next steps based on milestone status:

**If more phases remain:**
```
## Next Up

**Phase {X+1}: {Name}** -- {Goal}

Plan and execute next phase.
```

**If milestone complete:**
```
MILESTONE COMPLETE!

All {N} phases executed.

`/verify-milestone`
```
</step>

</process>

<context_efficiency>
**Why this works:**

Orchestrator context usage: ~10-15%
- Read plan.yaml task metadata (small)
- Analyze wave grouping and file_scope overlap (logic, no heavy reads)
- Fill template strings
- Spawn Task calls
- Collect results

Each subagent: Fresh 200k context
- Loads full task-{id}.md
- Loads templates, references
- Executes task with full capacity
- Reports checkpoint(task-{id}), commits

**No polling.** Task tool blocks until completion. No TaskOutput loops.

**No context bleed.** Orchestrator never reads workflow internals. Just paths and results.
</context_efficiency>

<failure_handling>
**Subagent fails mid-task:**
- checkpoint(task-{id}) won't be reported
- Orchestrator detects missing checkpoint
- Reports failure, asks user how to proceed

**Dependency chain breaks:**
- Wave 1 task fails
- Wave 2 tasks depending on it will likely fail
- Orchestrator can still attempt them (user choice)
- Or skip dependent tasks entirely

**All agents in wave fail:**
- Something systemic (git issues, permissions, etc.)
- Stop execution
- Report for manual investigation

**Checkpoint fails to resolve:**
- User can't approve or provides repeated issues
- Ask: "Skip this task?" or "Abort phase execution?"
- Record partial progress in plan.yaml
</failure_handling>

<resumption>
**Resuming interrupted execution:**

If phase execution was interrupted (context limit, user exit, error):

1. Run execute-phase again
2. discover_tasks finds completed tasks in plan.yaml (status: done)
3. Skips completed tasks
4. Resumes from first incomplete task
5. Continues wave-based execution

**plan.yaml tracks:**
- Last completed task
- Current wave
- Any pending checkpoints
</resumption>
