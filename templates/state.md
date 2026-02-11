# State Template

Template for `.planning/state.md` — the project's living memory.

---

## File Template

```markdown
# Project State

## Project Reference

See: .planning/project.md (updated [date])

**Core value:** [One-liner from project.md Core Value section]
**Current focus:** [Current phase name]

## Current Position

Phase: [X] of [Y] ([Phase name])
Task: [A] of [B] in current phase
Status: [Ready to plan / Planning / Ready to execute / In progress / Phase complete]
Last activity: [YYYY-MM-DD] — [What happened]

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total tasks completed: [N]
- Average duration: [X] min
- Total execution time: [X.X] hours

**By Phase:**

| Phase | Tasks | Total | Avg/Task |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 tasks: [durations]
- Trend: [Improving / Stable / Degrading]

*Updated after each task completion*

## Accumulated Context

### Decisions

Decisions are logged in project.md Key Decisions table.
Recent decisions affecting current work:

- [Phase X]: [Decision summary]
- [Phase Y]: [Decision summary]

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

None yet.

## Session Continuity

Last session: [YYYY-MM-DD HH:MM]
Stopped at: [Description of last completed action]
Resume file: [Path to .continue-here*.md if exists, otherwise "None"]
```

<purpose>

state.md is the project's short-term memory spanning all phases and sessions.

**Problem it solves:** Information is captured in summaries, issues, and decisions but not systematically consumed. Sessions start without context.

**Solution:** A single, small file that's:
- Read first in every workflow
- Updated after every significant action
- Contains digest of accumulated context
- Enables instant session restoration

</purpose>

<lifecycle>

**Creation:** After roadmap.md is created (during init)
- Reference project.md (read it for current context)
- Initialize empty accumulated context sections
- Set position to "Phase 1 ready to plan"

**Reading:** First step of every workflow
- progress: Present status to user
- plan: Inform planning decisions
- execute: Know current position
- transition: Know what's complete

**Writing:** After every significant action
- execute: After summary created
  - Update position (phase, task, status)
  - Note new decisions (detail in project.md)
  - Add blockers/concerns
- transition: After phase marked complete
  - Update progress bar
  - Clear resolved blockers
  - Refresh Project Reference date

</lifecycle>

<sections>

### Project Reference
Points to project.md for full context. Includes:
- Core value (the ONE thing that matters)
- Current focus (which phase)
- Last update date (triggers re-read if stale)

The agent reads project.md directly for requirements, constraints, and decisions.

### Current Position
Where we are right now:
- Phase X of Y — which phase
- Task A of B — which task within phase
- Status — current state
- Last activity — what happened most recently
- Progress bar — visual indicator of overall completion

Progress calculation: (completed tasks) / (total tasks across all phases) × 100%

### Performance Metrics
Track velocity to understand execution patterns:
- Total tasks completed
- Average duration per task
- Per-phase breakdown
- Recent trend (improving/stable/degrading)

Updated after each task completion.

### Accumulated Context

**Decisions:** Reference to project.md Key Decisions table, plus recent decisions summary for quick access. Full decision log lives in project.md.

**Pending Todos:** Ideas captured during sessions
- Count of pending todos
- Reference to .planning/todos/pending/
- Brief list if few, count if many

**Blockers/Concerns:** From "Next Phase Readiness" sections
- Issues that affect future work
- Prefix with originating phase
- Cleared when addressed

### Session Continuity
Enables instant resumption:
- When was last session
- What was last completed
- Is there a .continue-here file to resume from

</sections>

<size_constraint>

Keep state.md under 100 lines.

It's a DIGEST, not an archive. If accumulated context grows too large:
- Keep only 3-5 recent decisions in summary (full log in project.md)
- Keep only active blockers, remove resolved ones

The goal is "read once, know where we are" — if it's too long, that fails.

</size_constraint>

<guidelines>

**When created:**
- During project initialization (after roadmap.md)
- Reference project.md (extract core value and current focus)
- Initialize empty sections

**When read:**
- Every workflow starts by reading state.md
- Then read project.md for full context
- Provides instant context restoration

**When updated:**
- After each task execution (update position, note decisions, update issues/blockers)
- After phase transitions (update progress bar, clear resolved blockers, refresh project reference)

**Size management:**
- Keep under 100 lines total
- Recent decisions only in state.md (full log in project.md)
- Keep only active blockers

**Sections:**
- Project Reference: Pointer to project.md with core value
- Current Position: Where we are now (phase, task, status)
- Performance Metrics: Velocity tracking
- Accumulated Context: Recent decisions, pending todos, blockers
- Session Continuity: Resume information

</guidelines>
