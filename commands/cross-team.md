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

Only 1 unblocked task was found. Extract the task ID from the setup output (the `SINGLE_TASK_ID=...` line) and execute it directly using the Verifier-Gated Loop.

Run the single-task setup inline:

```!
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
PLAN_FILE=".claude/plan/plan.yaml"

# Parse the single task ID from the setup output above
TASK_ID="__PARSE_SINGLE_TASK_ID_FROM_OUTPUT__"

TASK_JSON=$(python3 -c "
import sys, json
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan, find_task
plan = load_plan('$PLAN_FILE')
_, task = find_task(plan, '$TASK_ID')
print(json.dumps(task))
" 2>/dev/null) || true

TASK_NAME=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name',''))" 2>/dev/null) || true
TEST_CMD=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['tests']['quantitative']['command'])" 2>/dev/null) || true
PROMPT_FILE=$(echo "$TASK_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['prompt_file'])" 2>/dev/null) || true
QUAL_CRITERIA=$(echo "$TASK_JSON" | python3 -c "
import sys, json
t = json.load(sys.stdin)
criteria = t.get('tests', {}).get('qualitative', {}).get('criteria', [])
for c in criteria:
    print(f'- {c}')
" 2>/dev/null) || true

MUST_HAVES=$(echo "$TASK_JSON" | python3 -c "
import sys, json
t = json.load(sys.stdin)
mh = t.get('must_haves', {})
truths = mh.get('truths', [])
artifacts = mh.get('artifacts', [])
key_links = mh.get('key_links', [])
if truths:
    print('TRUTHS (invariants that must hold):')
    for tr in truths: print(f'  - {tr}')
if artifacts:
    print('ARTIFACTS (files/outputs that must exist):')
    for a in artifacts: print(f'  - {a}')
if key_links:
    print('KEY LINKS (references):')
    for kl in key_links: print(f'  - {kl}')
" 2>/dev/null) || true

FULL_PROMPT_PATH=".claude/plan/${PROMPT_FILE}"
if [[ -n "$PROMPT_FILE" ]] && [[ -f "$FULL_PROMPT_PATH" ]]; then
  TASK_PROMPT=$(cat "$FULL_PROMPT_PATH")
else
  echo "PROMPT_NOT_FOUND: Task prompt file not found at $FULL_PROMPT_PATH"
  echo "CROSS_TEAM_FAILED"
  exit 0
fi

RAW_TASK_PROMPT="$TASK_PROMPT"

TASK_PROMPT="CRITICAL RULES — VIOLATION WILL BREAK THE LOOP:
- Do NOT modify .claude/plan/plan.yaml or any .claude/ state files
- Do NOT mark tasks as done or completed — the system handles all transitions
- Do NOT edit .claude/verifier-loop.local.md or .claude/verifier-token.secret

TDD-FIRST + OPENCODE MCP WORKFLOW (MANDATORY):
You MUST follow this execution order:
1. Write ALL tests first — unit tests, integration tests, edge cases. Every deliverable gets a test BEFORE any implementation code is written.
2. Spawn opencode agents concurrently using launch_opencode MCP tool — one agent per test file or implementation module. Example: launch_opencode(mode=\"build\", task=\"Make tests in <file> pass\")
3. Wait for all opencode agents to complete using wait_for_completion MCP tool.
4. Run the FULL test suite yourself to verify all tests pass: $TEST_CMD
5. If any tests fail, fix issues and re-run until green.
6. Only THEN spawn the Verifier subagent for final verification.

${MUST_HAVES:+MUST_HAVES FOR THIS TASK:
$MUST_HAVES
}
YOUR TASK:
$TASK_PROMPT"

# Mark task as in_progress
python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan, save_plan
plan = load_plan('$PLAN_FILE')
for phase in plan.get('phases', []):
    for task in phase.get('tasks', []):
        if str(task['id']) == '$TASK_ID':
            task['status'] = 'in_progress'
save_plan('$PLAN_FILE', plan)
print('Task $TASK_ID set to in_progress')
" 2>&1 || true

# Build JSON input and launch VGL in plan mode
export _VGL_TASK_PROMPT="$TASK_PROMPT"
export _VGL_RAW_TASK_PROMPT="$RAW_TASK_PROMPT"
export _VGL_TEST_CMD="$TEST_CMD"
export _VGL_QUAL_CRITERIA="$QUAL_CRITERIA"
export _VGL_TASK_ID="$TASK_ID"
export _VGL_NEXT_JSON="$TASK_JSON"
SETUP_JSON=$(python3 << 'PYEOF2'
import json, os
print(json.dumps({
    "prompt": os.environ["_VGL_TASK_PROMPT"],
    "verification_criteria": "Quantitative: {} must pass\nQualitative:\n{}".format(
        os.environ["_VGL_TEST_CMD"], os.environ["_VGL_QUAL_CRITERIA"]),
    "test_command": os.environ["_VGL_TEST_CMD"],
    "verifier_model": "opus",
    "max_iterations": 0,
    "plan_mode": True,
    "task_id": os.environ["_VGL_TASK_ID"],
    "task_json": os.environ["_VGL_NEXT_JSON"],
    "task_prompt_content": os.environ["_VGL_RAW_TASK_PROMPT"],
}))
PYEOF2
) || true

if [[ -z "$SETUP_JSON" ]]; then
  echo "SETUP_JSON_FAILED: Could not build setup JSON"
  echo "CROSS_TEAM_FAILED"
  exit 0
fi

"${PLUGIN_ROOT}/scripts/setup-verifier-loop.sh" --from-json "$SETUP_JSON" 2>&1 || {
  echo "SETUP_VGL_FAILED: setup-verifier-loop.sh failed"
  echo "CROSS_TEAM_FAILED"
  exit 0
}

echo "CROSS_OK"
```

**IMPORTANT:** Replace `__PARSE_SINGLE_TASK_ID_FROM_OUTPUT__` with the actual task ID shown in the `SINGLE_TASK_ID=...` line from the setup output above before running the script.

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

#### Step 3: Spawn Opencode Agents (Concurrent Implementation)
Use the `launch_opencode` MCP tool to spawn concurrent agents:
- One agent per test file or implementation module
- Each agent gets: "Make tests in {file} pass" as its task
- Agents work in parallel on non-overlapping file scopes
- Example: `launch_opencode(mode="build", task="Make tests in tests/auth.test.ts pass")`

#### Step 4: Wait for Completion
Use the `wait_for_completion` MCP tool to collect results from all opencode agents.
- Review each agent's output for errors or incomplete work
- If any agent failed, address its issues before proceeding

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

1. **Spawn worker teammates** for each dispatched task:
   - One teammate per task
   - Each worker gets: task prompt + VGL instructions + TDD-first workflow + session directory path
   - Workers write ALL tests first, spawn opencode agents via `launch_opencode` MCP tool, wait for completion via `wait_for_completion`, run full test suite, then spawn their own Verifier subagents
   - Workers report back with completion tokens or failure reasons

2. **Monitor worker messages** for:
   - `TASK_COMPLETE:{task_id}:{token}` — validate token, mark task completed
   - `TASK_FAILED:{task_id}:{reason}` — log failure, decide retry or skip

3. **Validate completion tokens**:
   - Read `.claude/vgl-sessions/task-{id}/verifier-token.secret` (line 1)
   - Compare with the token reported by the worker
   - Only mark complete if tokens match

4. **Mark tasks completed** via:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_utils.py" .claude/plan/plan.yaml --complete-task {task_id}
   ```

5. **Check for newly unblocked tasks** after each completion:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/get-unblocked-tasks.py" .claude/plan/plan.yaml
   ```
   - For each newly unblocked task, set up its VGL session and spawn a new worker

6. **When all tasks are done**:
   - Shut down all workers
   - Remove `.claude/vgl-team-active`
   - Remove `.claude/vgl-sessions/`
   - Report final status

### Critical Rules

- You are the LEAD — never write implementation code
- Only YOU update plan.yaml — workers must not touch it
- Validate every token before marking a task complete
- Workers with overlapping file scopes must NOT run simultaneously
- If a worker fails 3 times, skip the task and note it for the user
- Workers must follow TDD-first: tests before implementation, opencode for concurrency
- Verify must_haves (truths, artifacts, key_links) are satisfied before marking complete
