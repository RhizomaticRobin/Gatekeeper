---
description: "Cross the Bridge of Death — start a standalone Verifier-Gated Loop with TDD-first workflow for ad-hoc tasks"
argument-hint: "PROMPT --verification-criteria 'criteria' [--test-command 'cmd'] [--max-iterations N]"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/setup-verifier-loop.sh:*)", "Bash(python3:*)"]
---

Execute the setup script to initialize the Verifier-Gated Loop:

```!
_VGL_JSON=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/parse-args.py" <<'VGLEOF'
$ARGUMENTS
VGLEOF
) && "${CLAUDE_PLUGIN_ROOT}/scripts/setup-verifier-loop.sh" --from-json "$_VGL_JSON"
```

Work on the task described above. This is a Verifier-Gated Loop where you CANNOT complete the loop directly — completion authority is delegated to a Verifier subagent.

Follow this TDD-first workflow:

### Step 1: Write ALL Tests First (Red Phase)
Before writing ANY implementation code:
- Define the contract — what inputs produce what outputs
- Write tests for edge cases, error conditions, happy paths
- Write tests that validate must_haves truths if provided
- Tests MUST fail at this point — that is correct and expected

### Step 2: Spawn Opencode Agents (Concurrent Implementation)
Use the `launch_opencode` MCP tool to spawn concurrent agents:
- One agent per test file or implementation module
- Each agent gets: "Make tests in {file} pass" as its task
- Agents work in parallel on non-overlapping file scopes

### Step 3: Wait for Completion
Use the `wait_for_completion` MCP tool to collect results from all opencode agents.
- Review each agent's output for errors or incomplete work
- If any agent failed, address its issues before proceeding

### Step 4: Run Tests Locally (Green Phase)
Run the test command yourself to verify all tests pass:
- If any fail, fix the issues and re-run
- Do NOT proceed until the full suite is green

### Step 5: Spawn the Verifier
When ready, spawn the Verifier subagent to verify completion:
```
Task(subagent_type='general-purpose', model='opus',
     prompt=open('.claude/verifier-prompt.local.md').read())
```

The Verifier will:
- Run tests independently via `fetch-completion-token.sh`
- Check for TODO/FIXME/stub implementations
- Only receive the completion token if ALL checks pass
- Output the token to complete the loop, or reject with specific issues

### Critical Rules
- Follow TDD order strictly: tests FIRST, then implementation, then verification
- Use opencode concurrency — do not implement serially what can be done in parallel
- Trust the process and iterate until the Verifier approves
