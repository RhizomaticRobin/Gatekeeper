---
name: "gsd-vgl:autopilot"
description: "Launch autonomous execution via ralph.sh outer loop"
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# gsd-vgl:autopilot — Launch Autonomous Execution

You are the autopilot launcher. Your job is to configure execution settings, verify that planning artifacts exist, and launch `ralph.sh` in a new terminal for autonomous task execution.

---

## Step 1: Pre-Flight Checks

### Verify Planning Artifacts

Check that the minimum required files exist:

1. **`.planning/PROJECT.md`** — project definition (REQUIRED)
2. **`.planning/milestones/v1-REQUIREMENTS.md`** — requirements (REQUIRED)
3. **`.planning/milestones/v1-ROADMAP.md`** — roadmap (REQUIRED)
4. **`.planning/STATE.md`** — current state (REQUIRED)
5. **`.planning/config.json`** — configuration (REQUIRED)

If any are missing, tell the user:

> "Missing planning artifacts. Run `gsd-vgl:new-project` first to create the project plan."

### Verify Execution Plan

Check for an execution plan:

1. **`.claude/plan/plan.yaml`** — the task-level execution plan

If missing, note that ralph.sh will need to generate one from the roadmap.

### Check for ralph.sh

Locate `ralph.sh` in the plugin directory:
```bash
ls -la "$(dirname "$(dirname "$0")")/ralph.sh" 2>/dev/null || echo "NOT FOUND"
```

Also check common locations:
- `./ralph.sh`
- `./scripts/ralph.sh`
- The gsd-vgl plugin installation directory

If not found, inform the user and provide instructions for obtaining it.

---

## Step 2: Configure Settings

Read `.planning/config.json` and present current settings:

```
Current Configuration:
  Model Profile:    {quality|balanced|budget}
  Auto-commit:      {true|false}
  Auto-test:        {true|false}
  Pause on phase:   {true|false}
  Researcher agent: {enabled|disabled}
  Plan checker:     {enabled|disabled}
  Verifier agent:   {enabled|disabled}
```

Ask: "Want to adjust any settings before launch, or proceed with current config?"

If the user wants changes, update `.planning/config.json` accordingly. You can also direct them to `gsd-vgl:settings` for detailed configuration.

---

## Step 3: Detect Current State

Read `.planning/STATE.md` to determine where execution should begin:

- **NOT_STARTED** — Begin from Phase 1
- **IN_PROGRESS** — Resume from the current task in the current phase
- **PHASE_COMPLETE** — Start the next phase
- **BLOCKED** — Show the blocker and ask for resolution

Report the detected state:

> "Execution will {start from Phase 1 | resume Phase N, Task M | start Phase N+1}.
> Ready to launch?"

---

## Step 4: Launch ralph.sh

### Primary Method: terminal-launcher.js

Attempt to launch in a new terminal using `terminal-launcher.js`:

```bash
node "$(dirname "$(dirname "$0")")/terminal-launcher.js" \
  --script ralph.sh \
  --cwd "$(pwd)" \
  --title "gsd-vgl autopilot" \
  --config .planning/config.json
```

### Fallback: Direct Launch

If `terminal-launcher.js` is not available, launch ralph.sh directly:

```bash
# Construct the ralph.sh command with appropriate flags
RALPH_CMD="bash path/to/ralph.sh"
RALPH_CMD="$RALPH_CMD --project-dir $(pwd)"
RALPH_CMD="$RALPH_CMD --config .planning/config.json"
RALPH_CMD="$RALPH_CMD --state .planning/STATE.md"
```

Attempt these terminal emulators in order:
1. **tmux** (if running inside tmux):
   ```bash
   tmux new-window -n "gsd-autopilot" "$RALPH_CMD"
   ```
2. **screen**:
   ```bash
   screen -dmS gsd-autopilot bash -c "$RALPH_CMD"
   ```
3. **Background with nohup**:
   ```bash
   nohup $RALPH_CMD > .planning/autopilot.log 2>&1 &
   echo $! > .planning/autopilot.pid
   ```

### Last Resort: Same Terminal

If no terminal multiplexer is available:

> "No terminal multiplexer found. I can run ralph.sh in this terminal, but you won't be able to interact with Claude Code simultaneously. Proceed?"

If yes:
```bash
bash path/to/ralph.sh --project-dir "$(pwd)" --config .planning/config.json --state .planning/STATE.md
```

---

## Step 5: Post-Launch

After launching, inform the user:

> "Autopilot launched in {terminal method}.
>
> **Monitoring:**
> - `gsd-vgl:progress` — check status and progress
> - `.planning/STATE.md` — current execution state
> - `.planning/autopilot.log` — execution log (if background)
>
> **Controls:**
> - The autopilot will pause between phases if `pause_on_phase_complete` is enabled
> - To stop: kill the process or Ctrl+C in the autopilot terminal
> - To resume after stopping: run `gsd-vgl:autopilot` again (it will detect state)
>
> **Verification:**
> - `gsd-vgl:verify-milestone` — audit a completed milestone
> - `gsd-vgl:debug` — if something goes wrong"

---

## Error Handling

- If ralph.sh exits with an error, read the log and report the issue
- If STATE.md shows BLOCKED, present the blocker to the user
- If config.json is malformed, offer to regenerate via `gsd-vgl:settings`
- If the project directory has uncommitted changes and auto_commit is off, warn the user
