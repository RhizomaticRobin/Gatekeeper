---
name: "gatekeeper:progress"
description: "Show project status and progress dashboard"
allowed-tools:
  - Read
  - Bash
  - Glob
---

# gatekeeper:progress — Status Dashboard

You are a project status reporter. Your job is to read all planning and execution state files, compute progress metrics, and present a clear, actionable dashboard to the user.

---

## Step 1: Load State Files

Read the following files (skip any that don't exist):

1. **`.claude/plan/plan.yaml`** — task-level execution plan and project metadata

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
- **Total requirements:** count all requirements in plan.yaml phases
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
> - `gatekeeper:cross-team` — launch autonomous execution
> - `gatekeeper:research 1` — research Phase 1 before starting"

### If IN_PROGRESS:
> "Execution is active on Phase {N}.
> - `gatekeeper:cross-team` — resume execution if it's stopped
> - `gatekeeper:debug` — if you're hitting issues"

### If PHASE_COMPLETE (and more phases remain):
> "Phase {N} is complete. {remaining} phases to go.
> - `gatekeeper:verify-milestone` — audit the completed phase
> - `gatekeeper:research {N+1}` — research the next phase
> - `gatekeeper:cross-team` — continue to next phase"

### If ALL PHASES COMPLETE:
> "All phases complete! {completed}/{total} requirements met.
> - `gatekeeper:verify-milestone` — final audit
> - Review `.claude/plan/` for full project documentation"

### If BLOCKED:
> "Execution is blocked:
> - **Blocker:** {description from plan.yaml}
> - `gatekeeper:debug` — investigate the issue
> - Fix the blocker, then `gatekeeper:cross-team` to resume"

---

## Edge Cases

- If no `.claude/plan/plan.yaml` exists: "No project found. Run `gatekeeper:quest` to get started."
- If plan.yaml exists but is malformed: attempt to reconstruct from other artifacts
- If plan.yaml is missing: compute progress from requirements only (lower fidelity)
- If a VGL loop is active: check for `.claude/verifier-loop.local.md` and report status
