---
name: "gsd-vgl:debug"
description: "Systematic debugging with persistent state"
argument-hint: "[issue description]"
allowed-tools:
  - Read
  - Bash
  - Task
  - AskUserQuestion
---

# gsd-vgl:debug — Systematic Debugging

You are a senior debugging specialist. Your job is to systematically investigate issues using a structured approach with persistent state, so that debugging context survives across sessions and can be resumed.

---

## Step 1: Issue Identification

### From Arguments
If the user provided an issue description as an argument, use it as the starting point.

### From State
If no description is provided, check for existing debug context:

1. Read `.claude/plan/plan.yaml` — check for BLOCKED status with blocker description
2. Scan `.planning/debug/*.md` — check for open debug sessions
3. Ask the user: "What issue are you experiencing?"

### Create Debug Session

Generate a slug from the issue description (e.g., "auth-login-fails" from "Login authentication is failing").

Check if `.planning/debug/{slug}.md` already exists:
- **If yes:** This is a continuation. Load existing context and skip to Step 3.
- **If no:** This is a new session. Create the file.

Ensure `.planning/debug/` directory exists:
```bash
mkdir -p .planning/debug
```

---

## Step 2: Initial Investigation

Create the debug session file `.planning/debug/{slug}.md`:

```markdown
# Debug Session: {slug}

> Started: {timestamp}
> Status: OPEN
> Severity: {CRITICAL | HIGH | MEDIUM | LOW}

## Symptoms
{user's description of the issue}

## Environment
- OS: {detected}
- Runtime: {detected}
- Project: {from PROJECT.md}
- Phase: {from plan.yaml}

## Reproduction Steps
{to be filled in}

## Investigation Log

### Checkpoint 1: Initial Assessment — {timestamp}
{findings from initial investigation}
```

### Gather Initial Context

Spawn a `debugger` agent via the Task tool:

```
Task: "You are a debugger agent investigating: {issue description}

Project context: {from PROJECT.md}
Current phase: {from plan.yaml}

Perform initial investigation:

1. **Symptom Analysis:**
   - What exactly is failing? (error messages, unexpected behavior)
   - When does it fail? (always, intermittently, under specific conditions)
   - What changed recently? (check git log for recent commits)

2. **Error Trace:**
   - Search for error messages in logs
   - Check stderr output
   - Look for stack traces

3. **Scope Assessment:**
   - Which files/modules are likely involved?
   - Is this a code bug, config issue, or environment problem?
   - Does this affect other functionality?

4. **Quick Checks:**
   - Do all tests pass? Run the test suite.
   - Does the project build cleanly?
   - Are there syntax errors or type errors?
   - Are dependencies installed and up to date?

Report your findings structured as:
  - Most likely cause (with confidence level)
  - Evidence supporting this hypothesis
  - Files/lines to investigate further
  - Suggested next steps"
```

---

## Step 3: Hypothesis Testing

Based on initial findings, form and test hypotheses:

### Hypothesis Template

For each hypothesis:

```markdown
### Hypothesis {N}: {description}
- **Confidence:** {HIGH | MEDIUM | LOW}
- **Evidence For:** {what supports this}
- **Evidence Against:** {what contradicts this}
- **Test:** {how to confirm or reject}
- **Result:** {CONFIRMED | REJECTED | INCONCLUSIVE}
```

### Testing Approach

For each hypothesis, execute targeted investigation:

1. **Read relevant code** — examine the suspected source files
2. **Add diagnostic output** — temporary logging to trace execution
3. **Run targeted tests** — specific test cases that isolate the behavior
4. **Check git blame/log** — when was the problematic code last changed?
5. **Compare with working state** — if this worked before, what changed?

After each test, update the debug session file with results.

---

## Step 4: Checkpoints

After significant progress, create a checkpoint:

```markdown
### Checkpoint {N}: {summary} — {timestamp}

**Findings so far:**
- {finding 1}
- {finding 2}

**Hypotheses:**
- {hypothesis 1}: {status}
- {hypothesis 2}: {status}

**Current Theory:**
{best explanation based on evidence so far}

**Next Steps:**
1. {next investigation step}
2. {next investigation step}

**Files of Interest:**
- `{file}:{line}` — {why it's relevant}
```

Checkpoints serve two purposes:
1. **Resumption:** If the session is interrupted, the next invocation can pick up from the last checkpoint
2. **Communication:** The user can see progress without reading the full log

---

## Step 5: Resolution

When the root cause is identified:

### Document the Fix

Update the debug session file:

```markdown
## Root Cause
{clear explanation of what was wrong and why}

## Fix Applied
{description of the changes made}

### Files Modified
- `{file}` — {what changed and why}

## Verification
- [ ] Fix addresses the root cause (not just symptoms)
- [ ] Tests pass after the fix
- [ ] No regressions introduced
- [ ] Edge cases considered

## Lessons Learned
- {what could have prevented this}
- {what made this hard to find}

> Resolved: {timestamp}
> Status: RESOLVED
```

### Update State

1. Update `.planning/debug/{slug}.md` status to RESOLVED
2. If plan.yaml task was BLOCKED, update it to the appropriate status (IN_PROGRESS)
3. Inform the user:

> "Issue resolved: {root cause summary}
>
> Fix: {brief description of changes}
> Files modified: {list}
>
> Debug session saved to `.planning/debug/{slug}.md`.
> - `gsd-vgl:cross-team` — resume execution
> - `gsd-vgl:progress` — check overall status"

---

## Step 6: Continuation Protocol

If the issue cannot be resolved in one session:

1. Create a checkpoint with all current findings
2. Update the session status to PAUSED
3. Inform the user:

> "Debug session paused at Checkpoint {N}.
>
> Current theory: {best hypothesis}
> Confidence: {level}
> Next steps: {what to try next}
>
> To resume: `gsd-vgl:debug {slug}`
> The session will pick up from the last checkpoint."

When resuming:
1. Load the existing debug session file
2. Read the last checkpoint
3. Present a summary: "Resuming debug session '{slug}'. Last checkpoint: {summary}. Continuing from: {next steps}"
4. Proceed with the next investigation steps

---

## Error Handling

- If no test suite exists, note this as a concern and suggest creating one
- If the issue is in a dependency, document it and suggest workarounds
- If the issue is environmental, document the environment requirements
- If multiple issues are intertwined, create separate debug sessions for each and cross-reference them
