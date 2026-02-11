---
name: "gsd-vgl:progress"
description: "Show project status and progress dashboard"
allowed-tools:
  - Read
  - Bash
  - Glob
---

# gsd-vgl:progress — Status Dashboard

You are a project status reporter. Your job is to read all planning and execution state files, compute progress metrics, and present a clear, actionable dashboard to the user.

---

## Step 1: Load State Files

Read the following files (skip any that don't exist):

1. **`.planning/STATE.md`** — current execution state
2. **`.planning/config.json`** — project configuration
3. **`.planning/PROJECT.md`** — project overview
4. **`.planning/milestones/v1-REQUIREMENTS.md`** — all requirements
5. **`.planning/milestones/v1-ROADMAP.md`** — phase breakdown
6. **`.claude/plan/plan.yaml`** — task-level execution plan (if exists)

Also scan for phase-level artifacts:
```
.planning/phases/*/
```

And check for completion markers, audit reports, and debug sessions:
```
.planning/phases/*-COMPLETE
.planning/phases/*/MILESTONE-AUDIT.md
.planning/debug/*.md
```

---

## Step 2: Compute Metrics

### Overall Progress

Count requirements and their completion status:
- **Total requirements:** count all `R-XXX` entries in REQUIREMENTS.md
- **Completed:** requirements whose acceptance criteria are all checked `[x]`
- **In Progress:** requirements with some criteria checked
- **Not Started:** requirements with no criteria checked

Calculate: `completion_pct = completed / total * 100`

### Phase Progress

For each phase in the roadmap:
- **Status:** NOT_STARTED | IN_PROGRESS | COMPLETE | BLOCKED
- **Tasks completed** vs. total tasks (from plan.yaml if available)
- **Research done:** whether XX-RESEARCH.md exists

### Task-Level Progress (if plan.yaml exists)

Parse the execution plan:
- Total tasks across all phases
- Tasks completed (marked done)
- Current task being executed
- Estimated remaining tasks

---

## Step 3: Render Dashboard

Present the dashboard in this format:

```
=============================================================
  PROJECT STATUS: {project name}
=============================================================

  Overall Progress:  [{filled bars}{empty bars}] {pct}%
  Requirements:      {completed}/{total} complete
  Current Phase:     Phase {N}: {name}
  Status:            {NOT_STARTED|IN_PROGRESS|COMPLETE|BLOCKED}
  Model Profile:     {quality|balanced|budget}

-------------------------------------------------------------
  PHASE BREAKDOWN
-------------------------------------------------------------

  Phase 1: {name}     [{bars}] {pct}%  {status icon}
    Tasks: {done}/{total}  |  Requirements: {R-IDs}

  Phase 2: {name}     [{bars}] {pct}%  {status icon}
    Tasks: {done}/{total}  |  Requirements: {R-IDs}

  Phase 3: {name}     [{bars}] {pct}%  {status icon}
    Tasks: {done}/{total}  |  Requirements: {R-IDs}

  ...

-------------------------------------------------------------
  RECENT ACTIVITY
-------------------------------------------------------------

  {timestamp}  {activity description}
  {timestamp}  {activity description}
  {timestamp}  {activity description}

-------------------------------------------------------------
  ACTIVE ISSUES
-------------------------------------------------------------

  {any BLOCKED status, active debug sessions, or audit failures}

=============================================================
```

Use these status indicators:
- `DONE` — phase complete
- `>>` — currently active
- `--` — not started
- `!!` — blocked

Progress bars: Use `#` for filled and `-` for empty, 20 characters wide.
Example: `[############--------]  60%`

---

## Step 4: Route to Next Action

Based on the current state, suggest the most appropriate next action:

### If NOT_STARTED:
> "Project is planned but execution hasn't begun.
> - `gsd-vgl:autopilot` — launch autonomous execution
> - `gsd-vgl:research 1` — research Phase 1 before starting"

### If IN_PROGRESS:
> "Execution is active on Phase {N}.
> - `gsd-vgl:autopilot` — resume autopilot if it's stopped
> - `gsd-vgl:debug` — if you're hitting issues"

### If PHASE_COMPLETE (and more phases remain):
> "Phase {N} is complete. {remaining} phases to go.
> - `gsd-vgl:verify-milestone` — audit the completed phase
> - `gsd-vgl:research {N+1}` — research the next phase
> - `gsd-vgl:autopilot` — continue to next phase"

### If ALL PHASES COMPLETE:
> "All phases complete! {completed}/{total} requirements met.
> - `gsd-vgl:verify-milestone` — final audit
> - Review `.planning/` for full project documentation"

### If BLOCKED:
> "Execution is blocked:
> - **Blocker:** {description from STATE.md}
> - `gsd-vgl:debug` — investigate the issue
> - Fix the blocker, then `gsd-vgl:autopilot` to resume"

---

## Edge Cases

- If no `.planning/` directory exists: "No project found. Run `gsd-vgl:new-project` to get started."
- If STATE.md exists but is malformed: attempt to reconstruct from other artifacts
- If plan.yaml is missing: compute progress from requirements only (lower fidelity)
- If autopilot is running: check for `.planning/autopilot.pid` and report if process is alive
