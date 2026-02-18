---
description: "Cross the Bridge of Death — start a standalone Gatekeeper loop with TDD-first workflow for ad-hoc tasks"
argument-hint: "PROMPT --verification-criteria 'criteria' [--test-command 'cmd'] [--max-iterations N]"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/setup-verifier-loop.sh:*)", "Bash(python3:*)"]
---

Execute the setup script to initialize the Gatekeeper loop:

```!
_GK_JSON=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/parse-args.py" <<'GKEOF'
$ARGUMENTS
GKEOF
) && "${CLAUDE_PLUGIN_ROOT}/scripts/setup-verifier-loop.sh" --from-json "$_GK_JSON"
```

Work on the task described above. This is a Gatekeeper loop where you CANNOT complete the loop directly — completion authority is delegated to a Verifier subagent.

Follow this TDD-first workflow:

### Step 1: Write ALL Tests First (Red Phase)
Before writing ANY implementation code:
- Define the contract — what inputs produce what outputs
- Write tests for edge cases, error conditions, happy paths
- Write tests that validate must_haves truths if provided
- Tests MUST fail at this point — that is correct and expected

### Step 2: Dispatch Opencode Agents (1 Test Per Agent)
Use the `launch_opencode` MCP tool — dispatch 1 test per agent with guidance:
- Wave 1: launch fresh agents for independent tests (concurrent)
- Wave 2+: continue prior agent sessions for dependent tests — the agent that completed the dependency already has context
- If a test has multiple dependencies, continue the most significant one's session and tell it to review the others' work
- Each agent gets exactly 1 test file + specific implementation guidance

### Step 3: Wait for Completion (Per Wave)
Use `wait_for_completion` after each wave. Track `test → sessionId` for continuations.
- Review each agent's output for errors or incomplete work
- If any agent failed, address its issues before dispatching next wave
- If any agent has status "input_required", answer via `launch_opencode(sessionId=<id>, task="<answer>")`, then call `wait_for_completion()` again

### Step 4: Run Tests Locally (Green Phase)
Run the test command yourself to verify all tests pass:
- If any fail, fix the issues and re-run
- Do NOT proceed until the full suite is green

### Step 5: Spawn the Verifier
When ready, call the `verify_task` MCP tool:
```
verify_task(task_id="<task_id>")
```

The verifier MCP server handles everything internally:
- Loads the pre-generated verifier prompt (you never see it)
- Spawns an independent Claude Code agent with locked-down tools
- Runs tests independently via `fetch-completion-token.sh`
- Checks for TODO/FIXME/stub implementations
- Returns PASS (with token) or FAIL with specific issues

Parse the JSON result: if `status: "PASS"`, the loop completes. If `status: "FAIL"`, fix the issues in `details` and call `verify_task` again.

### Critical Rules
- Follow TDD order strictly: tests FIRST, then implementation, then verification
- Use opencode concurrency — do not implement serially what can be done in parallel
- Trust the process and iterate until the Verifier approves
